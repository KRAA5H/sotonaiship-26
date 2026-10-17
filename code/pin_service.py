"""Drop-a-pin location service for Kerbside.

When a report has no street, the bot texts the resident a short link. The
link opens a map; the resident taps where the PROBLEM is and confirms. We
save street, landmark, area and postcode against the report reference.

Privacy design, in priority order (see COMPLIANCE_LOCATION.md):
  - The service never sees a phone number, only an opaque report ref (R-0074).
  - The browser talks only to us and to the OpenStreetMap tile server. Every
    postcode and street lookup runs here, so third parties see our server.
  - Coordinates are discarded unless STORE_COORDINATES=1, and then rounded
    to 4 decimals (about 11 m). They are never logged.
  - No cookies, no analytics, no browser storage, no continuous tracking.

Functions the bot calls:
  create_location_link(report_ref) -> URL
  get_location(report_ref)        -> dict or None
  purge_expired()                 -> number of old links deleted

Run:
  python code/pin_service.py      serves on PIN_PORT (default 5007), behind HTTPS
"""

import hashlib
import hmac
import logging
import math
import os
import re
import secrets
import sqlite3
import threading
import time
import unicodedata
from collections import OrderedDict, deque
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from urllib.parse import quote

import requests
from flask import Flask, Response, jsonify, redirect, request, send_from_directory

try:  # same .env the rest of code/ uses; optional
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).with_name(".env"))
except ImportError:
    pass

HERE = Path(__file__).resolve().parent
STATIC_DIR = HERE / "pin" / "static"

REPORT_REF_RE = re.compile(r"^[A-Za-z0-9_.-]{1,40}$")
TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
POSTCODE_RE = re.compile(r"^[A-Z]{1,2}[0-9][A-Z0-9]? ?[0-9][A-Z]{2}$")

LINK_LIFETIME = timedelta(hours=2)
AFTER_CONFIRM = timedelta(minutes=10)  # time to fix a slip; a forwarded link dies fast
PURGE_AFTER = timedelta(days=7)

# Cheap local check before any third-party call: south, north, west, east.
CITY_BOX = (50.84, 50.99, -1.56, -1.28)
SOURCES = ("map", "gps", "postcode")
TEXT_CAP = 120

LIMITS = {"check": 30, "postcode": 20, "preview": 40, "confirm": 10, "bot": 120}

POSTCODES_IO = "https://api.postcodes.io/postcodes"
NOMINATIM_REVERSE = "https://nominatim.openstreetmap.org/reverse"

MSG = {
    "bad_link": "This link is not valid. Reply to our text with the road name instead.",
    "expired": "This link has expired. Reply to our text with the road name instead.",
    "bad_request": "Something was missing from that request. Please try again.",
    "bad_coords": "That pin position was not valid. Tap the map to place it again.",
    "outside_box": "That spot is outside Southampton. We can only take reports for the area Southampton City Council looks after.",
    "bad_postcode": "That does not look like a UK postcode. Check it and try again.",
    "postcode_unknown": "We could not find that postcode. Check it, or tap the map instead.",
    "postcode_down": "We could not look up that postcode just now. Tap the map instead.",
    "slow_down": "Too many tries in a short time. Please wait a minute and try again.",
}

ALLOWED_STATIC = {
    "pin.css", "pin.js",
    "vendor/leaflet/leaflet.js", "vendor/leaflet/leaflet.css",
    "vendor/leaflet/images/marker-icon.png", "vendor/leaflet/images/marker-icon-2x.png",
    "vendor/leaflet/images/marker-shadow.png", "vendor/leaflet/images/layers.png",
    "vendor/leaflet/images/layers-2x.png",
}

CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; "
       "img-src 'self' https://tile.openstreetmap.org data:; connect-src 'self'; "
       "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")


def _flag(name):
    return os.getenv(name, "").strip() == "1"


def _user_agent():
    return os.getenv("SOTONFIX_USER_AGENT") or "Kerbside-pin/1.0 (SotonShip 2026 hackathon prototype)"


# ---------------------------------------------------------------------------
# Time
# ---------------------------------------------------------------------------
def _now():
    return datetime.now(timezone.utc)


def _iso(dt):
    # One fixed format, so ISO strings compare correctly as text in SQL.
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Database: own file, no phone, name or email column anywhere
# ---------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS location_links (
    token_hash TEXT PRIMARY KEY,   -- sha256 of the token; the token itself is never stored
    report_ref TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_at    TEXT
);
CREATE TABLE IF NOT EXISTS report_locations (
    report_ref TEXT PRIMARY KEY,   -- one location per report; confirming again overwrites
    street     TEXT,
    landmark   TEXT,
    area       TEXT,
    postcode   TEXT,
    coverage   TEXT NOT NULL,      -- inside | unverified
    source     TEXT NOT NULL,      -- map | gps | postcode
    lat        REAL,               -- NULL unless STORE_COORDINATES=1
    lng        REAL,
    saved_at   TEXT NOT NULL
);
"""


def _db_path():
    return os.getenv("SOTONFIX_DB") or str(HERE / "pin.db")


def _connect():
    conn = sqlite3.connect(_db_path(), timeout=5, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_db():
    conn = _connect()
    try:
        conn.executescript(SCHEMA)
    finally:
        conn.close()


def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _valid_ref(report_ref):
    return isinstance(report_ref, str) and bool(REPORT_REF_RE.fullmatch(report_ref))


def create_location_link(report_ref):
    """A fresh 2 hour link for one report. Only the hash of the token is kept."""
    if not _valid_ref(report_ref):
        raise ValueError("report_ref must match ^[A-Za-z0-9_.-]{1,40}$")
    init_db()
    token = secrets.token_urlsafe(9)
    now = _now()
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO location_links (token_hash, report_ref, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (_hash(token), report_ref, _iso(now), _iso(now + LINK_LIFETIME)),
        )
    finally:
        conn.close()
    base = (os.getenv("BASE_URL") or "http://localhost:5007").rstrip("/")
    return f"{base}/p/{token}"


def get_location(report_ref):
    """What the resident confirmed for this report, or None."""
    if not _valid_ref(report_ref):
        return None
    init_db()
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM report_locations WHERE report_ref = ?", (report_ref,)).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    result = dict(row)
    if result["lat"] is None:
        result.pop("lat")
        result.pop("lng")
    return result


def as_report_location(loc):
    """One line for the report's location field: 'Lawn Road, near Portswood Park, SO17 2EZ'."""
    if not loc:
        return None
    parts = [loc.get("street") or loc.get("area")]
    near = loc.get("landmark") or (loc.get("area") if loc.get("street") else None)
    if near:
        parts.append(f"near {near}")
    parts.append(loc.get("postcode"))
    text = ", ".join(p for p in parts if p)
    return text or None


def purge_expired(now=None):
    """Delete links that expired more than 7 days ago. Saved locations are kept."""
    init_db()
    cutoff = _iso((now or _now()) - PURGE_AFTER)
    conn = _connect()
    try:
        return conn.execute("DELETE FROM location_links WHERE expires_at < ?", (cutoff,)).rowcount
    finally:
        conn.close()


def _link_state(token):
    """(200, row) for a live link, else (404 or 410, None)."""
    if not isinstance(token, str) or not TOKEN_RE.fullmatch(token):
        return 404, None
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM location_links WHERE token_hash = ?", (_hash(token),)).fetchone()
    finally:
        conn.close()
    if row is None:
        return 404, None
    if row["expires_at"] <= _iso(_now()):
        return 410, None
    return 200, dict(row)


def _save(link, place, source, lat, lng):
    now = _now()
    keep = _flag("STORE_COORDINATES")
    lat_s, lng_s = (round(lat, 4), round(lng, 4)) if keep else (None, None)
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """INSERT INTO report_locations
                   (report_ref, street, landmark, area, postcode, coverage, source, lat, lng, saved_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(report_ref) DO UPDATE SET
                   street = excluded.street, landmark = excluded.landmark, area = excluded.area,
                   postcode = excluded.postcode, coverage = excluded.coverage, source = excluded.source,
                   lat = excluded.lat, lng = excluded.lng, saved_at = excluded.saved_at""",
            (link["report_ref"], place["street"], place["landmark"], place["area"], place["postcode"],
             place["coverage"], source, lat_s, lng_s, _iso(now)),
        )
        # Shrink, never extend: a slip can be fixed, a forwarded link dies quickly.
        conn.execute(
            "UPDATE location_links SET used_at = ?, expires_at = MIN(expires_at, ?) WHERE token_hash = ?",
            (_iso(now), _iso(now + AFTER_CONFIRM), link["token_hash"]),
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Third parties: everything goes through _http_get_json, everything is untrusted
# ---------------------------------------------------------------------------
def _http_get_json(url, params=None, headers=None, timeout=5):
    """The ONLY function that talks to the outside world. Returns (status, json or None).
    Raises on network failure; callers treat that as 'lookup unavailable'."""
    response = requests.get(url, params=params, headers=headers, timeout=timeout)
    try:
        return response.status_code, response.json()
    except ValueError:
        return response.status_code, None


_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def clean(value):
    """Third-party text: strip control characters and angle brackets, cap at 120."""
    if not isinstance(value, str):
        return None
    value = "".join(ch for ch in value if unicodedata.category(ch) not in ("Cc", "Cf"))
    value = _CONTROL.sub("", value).replace("<", "").replace(">", "")
    value = " ".join(value.split())[:TEXT_CAP].strip()
    return value or None


class _OnePerSecond:
    """Nominatim allows one request per second across the whole app. acquire()
    gives up after `timeout` so a resident never waits behind a queue."""

    def __init__(self, gap=1.0):
        self._lock = threading.Lock()
        self._last = 0.0
        self.gap = gap

    def acquire(self, timeout):
        if not self._lock.acquire(timeout=timeout):
            return False
        wait = self._last + self.gap - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        return True

    def release(self):
        self._last = time.monotonic()
        self._lock.release()


class ReverseGeocoder:
    """Street, landmark and area from Nominatim, cached by rounded coordinate."""

    def __init__(self, cache_size=1000):
        self.lock = _OnePerSecond()  # tests swap this for a stub: locks can't be monkeypatched
        self._cache = OrderedDict()
        self._cache_lock = threading.Lock()
        self._cache_size = cache_size

    def lookup(self, lat, lng):
        key = (round(lat, 4), round(lng, 4))
        with self._cache_lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
        if not self.lock.acquire(timeout=2):
            return None  # busy: skip the street rather than make the resident wait
        try:
            status, data = _http_get_json(
                NOMINATIM_REVERSE,
                params={"format": "jsonv2", "lat": f"{key[0]:.4f}", "lon": f"{key[1]:.4f}",
                        "zoom": 18, "addressdetails": 1},
                headers={"User-Agent": _user_agent()},
            )
        except Exception:
            return None
        finally:
            self.lock.release()
        if status != 200 or not isinstance(data, dict):
            return None
        address = data.get("address") if isinstance(data.get("address"), dict) else {}
        street = clean(address.get("road") or address.get("pedestrian") or address.get("footway")
                       or address.get("path") or address.get("cycleway"))
        name = clean(data.get("name"))
        place = {
            "street": street,
            "landmark": name if name and (not street or name.lower() != street.lower()) else None,
            "area": clean(address.get("neighbourhood") or address.get("quarter") or address.get("suburb")),
            "postcode": clean(address.get("postcode")),
        }
        with self._cache_lock:
            self._cache[key] = place
            while len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)
        return place


geocoder = ReverseGeocoder()


def _nearest_postcode(lat, lng):
    """(postcode, admin_district) for the nearest postcode within 1000 m, or None if unknown."""
    try:
        status, data = _http_get_json(
            POSTCODES_IO,
            params={"lon": f"{lng:.5f}", "lat": f"{lat:.5f}", "radius": 1000, "limit": 1},
            headers={"User-Agent": _user_agent()},
        )
    except Exception:
        return None
    if status != 200 or not isinstance(data, dict) or not data.get("result"):
        return None
    first = data["result"][0] if isinstance(data["result"], list) else None
    if not isinstance(first, dict):
        return None
    return clean(first.get("postcode")), clean(first.get("admin_district"))


def _in_box(lat, lng):
    south, north, west, east = CITY_BOX
    return south <= lat <= north and west <= lng <= east


def _coords(body):
    """Finite JSON numbers in range, else None. Strings, booleans, NaN and infinity are refused."""
    lat, lng = body.get("lat"), body.get("lng")
    for v in (lat, lng):
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return None
    lat, lng = float(lat), float(lng)
    if not (math.isfinite(lat) and math.isfinite(lng)):
        return None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None
    return lat, lng


def assess(lat, lng):
    """(status, payload). Run on preview AND confirm: the browser's verdict is never trusted.
    The payload never contains coordinates."""
    if not _in_box(lat, lng):
        return 422, {"ok": False, "error": MSG["outside_box"]}  # no third-party call at all
    nearest = _nearest_postcode(lat, lng)
    coverage = "unverified"
    postcode = None
    if nearest:
        postcode, district = nearest
        if district and district != "Southampton":
            return 422, {"ok": False, "error":
                         f"That spot looks like it is in {district}, not Southampton. "
                         f"Please report it to {district} instead."}
        if district == "Southampton":
            coverage = "inside"
    place = geocoder.lookup(lat, lng) or {"street": None, "landmark": None, "area": None, "postcode": None}
    return 200, {
        "ok": True,
        "coverage": coverage,
        "street": place["street"],
        "landmark": place["landmark"],
        "area": place["area"],
        "postcode": postcode or place["postcode"],
    }


# ---------------------------------------------------------------------------
# Rate limiting: in memory, per IP and endpoint, bounded
# ---------------------------------------------------------------------------
class RateLimiter:
    def __init__(self, limits, window=60.0, max_keys=10000):
        self.limits = limits
        self.window = window
        self.max_keys = max_keys
        self._hits = OrderedDict()
        self._lock = threading.Lock()

    def allow(self, ip, bucket):
        now = time.monotonic()
        key = (ip, bucket)
        with self._lock:
            hits = self._hits.get(key)
            if hits is None:
                hits = self._hits[key] = deque()
                while len(self._hits) > self.max_keys:  # bounded: forget the oldest clients
                    self._hits.popitem(last=False)
            else:
                self._hits.move_to_end(key)
            while hits and hits[0] <= now - self.window:
                hits.popleft()
            if len(hits) >= self.limits[bucket]:
                return False
            hits.append(now)
            return True


# ---------------------------------------------------------------------------
# Logging: the token is a key, so keep it out of access logs
# ---------------------------------------------------------------------------
class _RedactTokens(logging.Filter):
    _PATH = re.compile(r"/p/[A-Za-z0-9_-]+")

    def filter(self, record):
        message = record.getMessage()
        if "/p/" in message:
            record.msg, record.args = self._PATH.sub("/p/[redacted]", message), ()
        return True


# ---------------------------------------------------------------------------
# The app
# ---------------------------------------------------------------------------
def _err(status, message):
    return jsonify({"ok": False, "error": message}), status


def create_app():
    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = 4096  # every body here is a few numbers
    limiter = RateLimiter(LIMITS)
    app.extensions["pin_limiter"] = limiter
    if _flag("TRUST_PROXY"):
        # Behind a tunnel or reverse proxy every request would otherwise share one IP.
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    logging.getLogger("werkzeug").addFilter(_RedactTokens())

    init_db()
    purge_expired()

    def guard(bucket):
        """Rate limit, then a JSON object body. Returns (body, None) or (None, error response)."""
        if not limiter.allow(request.remote_addr or "?", bucket):
            return None, _err(429, MSG["slow_down"])
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return None, _err(400, MSG["bad_request"])
        return body, None

    def live_link(body):
        status, link = _link_state(body.get("token"))
        if status == 404:
            return None, _err(404, MSG["bad_link"])
        if status == 410:
            return None, _err(410, MSG["expired"])
        return link, None

    @app.after_request
    def headers(response):
        response.headers["Content-Security-Policy"] = CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Not no-referrer: the OSM tile server needs our origin. strict-origin
        # still keeps the token path out of every Referer header.
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(self), camera=(), microphone=(), payment=()"
        if request.path.startswith(("/p/", "/api/")):
            response.headers["Cache-Control"] = "no-store"
        if request.is_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    @app.get("/p/<token>")
    def page(token):
        # Same page for every token: the page asks /api/check, so a bad link
        # reveals nothing here.
        return send_from_directory(STATIC_DIR, "pin.html")

    @app.get("/static/<path:name>")
    def static_file(name):
        if name not in ALLOWED_STATIC:
            return Response("Not found", 404, mimetype="text/plain")
        return send_from_directory(STATIC_DIR, name)

    @app.post("/api/check")
    def check():
        body, error = guard("check")
        if error:
            return error
        link, error = live_link(body)
        if error:
            return error
        return jsonify({"ok": True})

    @app.post("/api/postcode")
    def postcode():
        body, error = guard("postcode")
        if error:
            return error
        link, error = live_link(body)
        if error:
            return error
        raw = body.get("postcode")
        pc = " ".join(raw.upper().split()) if isinstance(raw, str) else ""
        if not POSTCODE_RE.fullmatch(pc):
            return _err(400, MSG["bad_postcode"])
        try:
            status, data = _http_get_json(f"{POSTCODES_IO}/{quote(pc)}",
                                          headers={"User-Agent": _user_agent()})
        except Exception:
            return _err(503, MSG["postcode_down"])
        if status == 404:
            return _err(422, MSG["postcode_unknown"])
        result = data.get("result") if status == 200 and isinstance(data, dict) else None
        if not isinstance(result, dict):
            return _err(503, MSG["postcode_down"])
        lat, lng = result.get("latitude"), result.get("longitude")
        coords = _coords({"lat": lat, "lng": lng})
        if coords is None:
            return _err(422, MSG["postcode_unknown"])
        district = clean(result.get("admin_district"))
        if not _in_box(*coords):
            return _err(422, MSG["outside_box"])
        if district and district != "Southampton":
            return _err(422, f"That postcode is in {district}, not Southampton. "
                             f"Please report it to {district} instead.")
        return jsonify({"ok": True, "lat": coords[0], "lng": coords[1]})

    @app.post("/api/preview")
    def preview():
        body, error = guard("preview")
        if error:
            return error
        link, error = live_link(body)
        if error:
            return error
        coords = _coords(body)
        if coords is None:
            return _err(400, MSG["bad_coords"])
        status, payload = assess(*coords)
        return jsonify(payload), status

    @app.post("/api/confirm")
    def confirm():
        body, error = guard("confirm")
        if error:
            return error
        link, error = live_link(body)
        if error:
            return error
        coords = _coords(body)
        if coords is None:
            return _err(400, MSG["bad_coords"])
        source = body.get("source") if body.get("source") in SOURCES else "map"
        status, place = assess(*coords)  # re-run every check: never trust the browser
        if status != 200:
            return jsonify(place), status
        _save(link, place, source, *coords)  # writes only the link's own report_ref
        saved = {k: place[k] for k in ("street", "landmark", "area", "postcode", "coverage")}
        return jsonify({"ok": True, "saved": saved, "change_minutes": int(AFTER_CONFIRM.total_seconds() // 60)})

    @app.get("/api/location/<report_ref>")
    def bot_location(report_ref):
        key = os.getenv("BOT_API_KEY", "")
        if not key:
            return Response("Not found", 404, mimetype="text/plain")  # off unless configured
        if not limiter.allow(request.remote_addr or "?", "bot"):
            return _err(429, MSG["slow_down"])
        given = request.headers.get("X-Api-Key", "")
        if not hmac.compare_digest(given.encode(), key.encode()):
            return _err(401, "unauthorised")
        if not _valid_ref(report_ref):
            return _err(400, "bad report_ref")
        loc = get_location(report_ref)
        if loc is None:
            return _err(404, "no location saved for that report")
        return jsonify({"ok": True, "location": loc, "location_text": as_report_location(loc)})

    @app.get("/privacy")
    def privacy():
        return Response(privacy_html(), mimetype="text/html")

    @app.get("/demo")
    def demo():
        if not _flag("DEMO"):
            return Response("Not found", 404, mimetype="text/plain")
        url = create_location_link("DEMO-1")
        return redirect("/p/" + url.rsplit("/p/", 1)[1], code=302)

    return app


def privacy_html():
    controller = escape(os.getenv("CONTROLLER_NAME") or "[set CONTROLLER_NAME]")
    contact = escape(os.getenv("CONTACT_EMAIL") or "[set CONTACT_EMAIL]")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>How we use your location</title>
<link rel="stylesheet" href="/static/pin.css">
</head>
<body class="doc">
<main>
<h1>How we use your location</h1>
<p>This page lets you show us where a street problem is, so the council can find it and fix it.</p>

<h2>Who is responsible</h2>
<p>The data controller is <strong>{controller}</strong>. Contact: <strong>{contact}</strong>.</p>

<h2>What we keep</h2>
<p>For your report we keep the street, a nearby landmark, the area and the postcode of the pin you place. We do not keep the exact map position unless the service owner has switched that on, and even then it is rounded to about 11 metres. We never see your phone number on this page. The link only knows a report reference.</p>

<h2>Your phone's location</h2>
<p>Using your phone's location is optional. Your phone asks your permission first, we take one reading only when you press the button, and we use it only to place the pin. We never track you. You can always tap the map instead, or reply to our text with the road name.</p>

<h2>Who else is involved</h2>
<ul>
<li><strong>OpenStreetMap</strong> provides the map pictures. Your browser loads them directly, so the OpenStreetMap tile server sees your internet address, as with any website.</li>
<li><strong>postcodes.io</strong> tells us the nearest postcode and which council area the pin is in.</li>
<li><strong>Nominatim</strong>, run by the OpenStreetMap Foundation, tells us the street name.</li>
</ul>
<p>Our server makes those last two lookups, so those services see our server, not you.</p>

<h2>Why we use it and for how long</h2>
<p>We use it only to deal with your street report, which is part of the council's public task of looking after the city's streets. Links stop working after 2 hours, or 10 minutes after you confirm, and are deleted a week after that. The street details stay with your report for as long as the report is kept.</p>

<h2>No tracking</h2>
<p>This page sets no cookies, uses no analytics and stores nothing in your browser.</p>

<h2>Your rights</h2>
<p>You can ask to see, correct or delete what we hold, or object to how we use it, by contacting {contact}. If you are unhappy with how we handle your data, you can complain to the Information Commissioner's Office at <a href="https://ico.org.uk/make-a-complaint/">ico.org.uk</a>.</p>
</main>
</body>
</html>
"""


if __name__ == "__main__":
    create_app().run(host=os.getenv("PIN_HOST", "127.0.0.1"),
                     port=int(os.getenv("PIN_PORT") or "5007"), debug=False)

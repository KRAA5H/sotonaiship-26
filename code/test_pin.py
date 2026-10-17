"""Tests for pin_service.py and the pin page. Standard library plus Flask, no network.

The one function that talks to third parties (_http_get_json) is mocked, and
the Nominatim one-per-second lock is swapped for a stub so nothing sleeps.

Run:
  python code/test_pin.py
"""

import json
import os
import re
import sqlite3
import sys
import tempfile
import unittest
import unittest.mock
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pin_service

STATIC = Path(pin_service.STATIC_DIR)
INSIDE = (50.9069, -1.4058)    # Windsor Terrace, city centre
LONDON = (51.5010, -0.1416)
EASTLEIGH = (50.9680, -1.3500)  # inside the cheap box, but another council


class FreeLock:
    """Stands in for the one-per-second lock: Python locks can't be monkeypatched."""
    def acquire(self, timeout):
        return True

    def release(self):
        pass


class FakeWeb:
    """Answers the three third-party calls and counts them."""
    def __init__(self):
        self.calls = []
        self.district = "Southampton"
        self.postcode = "SO14 7BQ"
        self.road = "Windsor Terrace"
        self.name = "The Bargate"
        self.area = "Cultural Quarter"
        self.down = False
        self.lookup = {"SO14 7BQ": ("Southampton", 50.9069, -1.4058),
                       "SO50 9YN": ("Eastleigh", 50.9690, -1.3510),
                       "SW1A 1AA": ("Westminster", 51.5010, -0.1416)}

    def __call__(self, url, params=None, headers=None, timeout=5):
        self.calls.append(url)
        assert headers and headers.get("User-Agent"), "third parties must get a real User-Agent"
        if self.down:
            raise OSError("network down")
        if url.startswith(pin_service.NOMINATIM_REVERSE):
            return 200, {"name": self.name, "address": {
                "road": self.road, "quarter": self.area, "postcode": self.postcode}}
        if url == pin_service.POSTCODES_IO:
            return 200, {"status": 200, "result": [
                {"postcode": self.postcode, "admin_district": self.district}]}
        pc = url.rsplit("/", 1)[1].replace("%20", " ")
        if pc in self.lookup:
            district, lat, lng = self.lookup[pc]
            return 200, {"status": 200, "result": {"postcode": pc, "admin_district": district,
                                                   "latitude": lat, "longitude": lng}}
        return 404, {"status": 404, "error": "Postcode not found"}


class PinCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = unittest.mock.patch.dict(os.environ, {
            "SOTONFIX_DB": str(Path(self.tmp.name) / "pin.db"),
            "BASE_URL": "https://pin.example",
        })
        self.env.start()
        for name in ("STORE_COORDINATES", "BOT_API_KEY", "DEMO", "CONTROLLER_NAME", "CONTACT_EMAIL", "TRUST_PROXY"):
            os.environ.pop(name, None)
        self.web = FakeWeb()
        self.http = unittest.mock.patch.object(pin_service, "_http_get_json", self.web)
        self.http.start()
        pin_service.geocoder = pin_service.ReverseGeocoder()
        pin_service.geocoder.lock = FreeLock()
        self.app = pin_service.create_app()
        self.client = self.app.test_client()

    def tearDown(self):
        self.http.stop()
        self.env.stop()
        self.tmp.cleanup()

    # helpers
    def link(self, ref="R-0074"):
        return pin_service.create_location_link(ref).rsplit("/p/", 1)[1]

    def post(self, path, **body):
        return self.client.post(path, json=body)

    def db(self, sql, args=()):
        conn = sqlite3.connect(os.environ["SOTONFIX_DB"])
        conn.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in conn.execute(sql, args)]
        finally:
            conn.close()

    def expire(self, token, delta):
        conn = sqlite3.connect(os.environ["SOTONFIX_DB"])
        try:
            conn.execute("UPDATE location_links SET expires_at = ? WHERE token_hash = ?",
                         (pin_service._iso(pin_service._now() + delta), pin_service._hash(token)))
            conn.commit()
        finally:
            conn.close()


class Storage(PinCase):
    def test_token_is_stored_hashed_only(self):
        url = pin_service.create_location_link("R-0074")
        self.assertTrue(url.startswith("https://pin.example/p/"))
        token = url.rsplit("/p/", 1)[1]
        rows = self.db("SELECT * FROM location_links")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["token_hash"], pin_service._hash(token))
        self.assertNotIn(token, json.dumps(rows))

    def test_no_personal_columns(self):
        pin_service.init_db()
        for table in ("location_links", "report_locations"):
            cols = {r["name"].lower() for r in self.db(f"PRAGMA table_info({table})")}
            for banned in ("phone", "name", "email", "number", "handle"):
                self.assertFalse(any(banned in c for c in cols), f"{table} has {banned}: {cols}")

    def test_report_ref_validation(self):
        for bad in ("R 0074", "R-0074;DROP", "../etc/passwd", "a/b", "", "x" * 41, None, 74, "R-0074\n"):
            with self.assertRaises(ValueError, msg=repr(bad)):
                pin_service.create_location_link(bad)
            self.assertIsNone(pin_service.get_location(bad))
        pin_service.create_location_link("R-0074")
        pin_service.create_location_link("demo_1.v2")

    def test_purge_removes_old_links_only(self):
        old, recent, live = self.link("R-1"), self.link("R-2"), self.link("R-3")
        self.expire(old, -timedelta(days=8))
        self.expire(recent, -timedelta(days=6))
        self.assertEqual(pin_service.purge_expired(), 1)
        left = {r["report_ref"] for r in self.db("SELECT report_ref FROM location_links")}
        self.assertEqual(left, {"R-2", "R-3"})


class Check(PinCase):
    def test_states(self):
        token = self.link()
        self.assertEqual(self.post("/api/check", token=token).status_code, 200)
        self.assertEqual(self.post("/api/check", token="nope-nope-nope").status_code, 404)
        self.assertEqual(self.post("/api/check", token=12345).status_code, 404)
        self.assertEqual(self.post("/api/check", token=["a"]).status_code, 404)
        self.assertEqual(self.post("/api/check").status_code, 404)
        self.assertEqual(self.client.post("/api/check", data="not json").status_code, 400)
        self.expire(token, -timedelta(seconds=1))
        r = self.post("/api/check", token=token)
        self.assertEqual(r.status_code, 410)
        self.assertIn("expired", r.get_json()["error"])


class Preview(PinCase):
    def test_returns_place_and_never_coordinates(self):
        r = self.post("/api/preview", token=self.link(), lat=INSIDE[0], lng=INSIDE[1])
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertEqual((d["street"], d["postcode"], d["coverage"]), ("Windsor Terrace", "SO14 7BQ", "inside"))
        self.assertEqual(d["landmark"], "The Bargate")
        self.assertEqual(d["area"], "Cultural Quarter")
        body = r.get_data(as_text=True)
        self.assertNotIn("lat", d)
        self.assertNotIn("lng", d)
        self.assertNotIn("50.906", body)
        self.assertNotIn("-1.405", body)

    def test_london_rejected_with_no_third_party_call(self):
        token = self.link()
        for path in ("/api/preview", "/api/confirm"):
            r = self.post(path, token=token, lat=LONDON[0], lng=LONDON[1])
            self.assertEqual(r.status_code, 422)
        self.assertEqual(self.web.calls, [])

    def test_bad_coordinates_rejected(self):
        token = self.link()
        for lat, lng in ((float("nan"), 1), ("50.9", "-1.4"), (True, -1.4), (None, -1.4), (91, 0), (50.9, 181)):
            r = self.post("/api/preview", token=token, lat=lat, lng=lng)
            self.assertEqual(r.status_code, 400, (lat, lng))
        for raw in ('{"token": "%s", "lat": NaN, "lng": -1.4}', '{"token": "%s", "lat": Infinity, "lng": -1.4}',
                    '{"token": "%s", "lat": 50.9, "lng": -Infinity}'):
            r = self.client.post("/api/preview", data=raw % token, content_type="application/json")
            self.assertEqual(r.status_code, 400, raw)
        self.assertEqual(self.web.calls, [])

    def test_hostile_geocoder_text_is_cleaned_and_capped(self):
        self.web.road = "<script>alert(1)</script>Evil\x00 Road" + "x" * 300
        self.web.name = "‮Sneaky <b>Landmark</b>"
        d = self.post("/api/preview", token=self.link(), lat=INSIDE[0], lng=INSIDE[1]).get_json()
        for value in (d["street"], d["landmark"]):
            self.assertNotIn("<", value)
            self.assertNotIn(">", value)
            self.assertNotIn("\x00", value)
            self.assertNotIn("‮", value)
            self.assertLessEqual(len(value), 120)
        self.assertTrue(d["street"].startswith("scriptalert(1)/scriptEvil Road"))


class Confirm(PinCase):
    def confirm(self, token, lat=INSIDE[0], lng=INSIDE[1], **extra):
        return self.post("/api/confirm", token=token, lat=lat, lng=lng, **extra)

    def test_default_stores_place_not_coordinates(self):
        r = self.confirm(self.link(), source="gps")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["saved"]["street"], "Windsor Terrace")
        self.assertNotIn("50.906", r.get_data(as_text=True))
        row = self.db("SELECT * FROM report_locations")[0]
        self.assertEqual((row["report_ref"], row["street"], row["postcode"], row["source"]),
                         ("R-0074", "Windsor Terrace", "SO14 7BQ", "gps"))
        self.assertIsNone(row["lat"])
        self.assertIsNone(row["lng"])
        loc = pin_service.get_location("R-0074")
        self.assertNotIn("lat", loc)
        self.assertEqual(pin_service.as_report_location(loc), "Windsor Terrace, near The Bargate, SO14 7BQ")

    def test_store_coordinates_rounds_to_4_decimals(self):
        os.environ["STORE_COORDINATES"] = "1"
        self.confirm(self.link(), lat=50.906932123, lng=-1.405823987)
        row = self.db("SELECT lat, lng FROM report_locations")[0]
        self.assertEqual((row["lat"], row["lng"]), (50.9069, -1.4058))

    def test_unknown_source_becomes_map(self):
        self.confirm(self.link(), source="<script>")
        self.assertEqual(self.db("SELECT source FROM report_locations")[0]["source"], "map")

    def test_other_council_rejected_server_side(self):
        self.web.district = "Eastleigh"
        r = self.confirm(self.link(), lat=EASTLEIGH[0], lng=EASTLEIGH[1], coverage="inside")
        self.assertEqual(r.status_code, 422)
        self.assertIn("Eastleigh", r.get_json()["error"])
        self.assertEqual(self.db("SELECT * FROM report_locations"), [])

    def test_link_shrinks_and_reconfirm_overwrites(self):
        token = self.link()
        self.confirm(token)
        expires = self.db("SELECT expires_at FROM location_links")[0]["expires_at"]
        self.assertLessEqual(expires, pin_service._iso(pin_service._now() + timedelta(minutes=10, seconds=1)))
        self.web.road = "Above Bar Street"
        self.assertEqual(self.confirm(token, lat=50.9080, lng=-1.4040).status_code, 200)  # pin moved
        rows = self.db("SELECT * FROM report_locations")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["street"], "Above Bar Street")
        self.assertEqual(self.db("SELECT expires_at FROM location_links")[0]["expires_at"] <= expires, True)

    def test_one_link_cannot_write_another_report(self):
        token = self.link("R-0001")
        self.link("R-0002")
        self.confirm(token, report_ref="R-0002")
        self.assertEqual([r["report_ref"] for r in self.db("SELECT report_ref FROM report_locations")], ["R-0001"])
        self.assertIsNone(pin_service.get_location("R-0002"))

    def test_both_geocoders_down_still_saves_unverified(self):
        self.web.down = True
        r = self.confirm(self.link())
        self.assertEqual(r.status_code, 200)
        row = self.db("SELECT * FROM report_locations")[0]
        self.assertEqual(row["coverage"], "unverified")
        self.assertIsNone(row["street"])

    def test_expired_link_cannot_confirm(self):
        token = self.link()
        self.expire(token, -timedelta(seconds=1))
        self.assertEqual(self.confirm(token).status_code, 410)
        self.assertEqual(self.db("SELECT * FROM report_locations"), [])


class Postcode(PinCase):
    def test_search(self):
        token = self.link()
        r = self.post("/api/postcode", token=token, postcode=" so14 7bq ")
        self.assertEqual(r.status_code, 200)
        self.assertEqual((r.get_json()["lat"], r.get_json()["lng"]), (50.9069, -1.4058))

        r = self.post("/api/postcode", token=token, postcode="SO50 9YN")
        self.assertEqual(r.status_code, 422)
        self.assertIn("Eastleigh", r.get_json()["error"])
        self.assertEqual(self.post("/api/postcode", token=token, postcode="SW1A 1AA").status_code, 422)

        calls = len(self.web.calls)
        for bad in ("hello", "SO14 7BQ; DROP", "../../x", 12345, "S014 7BQ"):
            self.assertEqual(self.post("/api/postcode", token=token, postcode=bad).status_code, 400, bad)
        self.assertEqual(len(self.web.calls), calls, "malformed postcodes never leave the server")

        self.assertEqual(self.post("/api/postcode", token=token, postcode="SO99 9ZZ").status_code, 422)
        self.assertEqual(self.post("/api/postcode", token="bad-token-x", postcode="SO14 7BQ").status_code, 404)


class Security(PinCase):
    def test_rate_limit(self):
        token = self.link()
        codes = [self.post("/api/check", token=token).status_code for _ in range(31)]
        self.assertEqual(codes[:30], [200] * 30)
        self.assertEqual(codes[30], 429)
        codes = [self.post("/api/confirm", token=token, lat=INSIDE[0], lng=INSIDE[1]).status_code for _ in range(11)]
        self.assertEqual(codes[-1], 429)

    def test_headers(self):
        token = self.link()
        for r in (self.client.get(f"/p/{token}"), self.post("/api/check", token=token),
                  self.client.get("/privacy"), self.client.get("/static/pin.js")):
            csp = r.headers["Content-Security-Policy"]
            self.assertIn("default-src 'none'", csp)
            self.assertIn("script-src 'self'", csp)
            self.assertIn("img-src 'self' https://tile.openstreetmap.org data:", csp)
            self.assertIn("frame-ancestors 'none'", csp)
            self.assertNotIn("unsafe-inline", csp)
            self.assertNotIn("unsafe-eval", csp)
            self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")
            self.assertEqual(r.headers["Referrer-Policy"], "strict-origin-when-cross-origin")
            self.assertEqual(r.headers["Permissions-Policy"], "geolocation=(self), camera=(), microphone=(), payment=()")
            self.assertNotIn("Set-Cookie", r.headers)
        self.assertEqual(self.client.get(f"/p/{token}").headers["Cache-Control"], "no-store")
        self.assertEqual(self.post("/api/check", token=token).headers["Cache-Control"], "no-store")
        self.assertNotIn("Strict-Transport-Security", self.client.get("/privacy").headers)
        secure = self.client.get("/privacy", base_url="https://pin.example")
        self.assertIn("max-age=", secure.headers["Strict-Transport-Security"])

    def test_static_allowlist(self):
        self.assertEqual(self.client.get("/static/pin.css").status_code, 200)
        self.assertEqual(self.client.get("/static/vendor/leaflet/images/marker-icon.png").status_code, 200)
        for bad in ("/static/../pin_service.py", "/static/vendor/leaflet/LICENSE", "/static/pin.html",
                    "/static/%2e%2e/pin_service.py"):
            self.assertEqual(self.client.get(bad).status_code, 404, bad)

    def test_page_served_for_any_token_without_leaking(self):
        good = self.client.get(f"/p/{self.link()}").get_data(as_text=True)
        bad = self.client.get("/p/unknown-token-here").get_data(as_text=True)
        self.assertEqual(good, bad)

    def test_token_redacted_from_access_log(self):
        import logging
        record = logging.LogRecord("werkzeug", logging.INFO, __file__, 1,
                                   '%s - - "%s" %s', ("127.0.0.1", "GET /p/AbCdEf123_- HTTP/1.1", "200"), None)
        pin_service._RedactTokens().filter(record)
        self.assertNotIn("AbCdEf123", record.getMessage())


class StaticFiles(unittest.TestCase):
    html = (STATIC / "pin.html").read_text(encoding="utf-8")
    js = (STATIC / "pin.js").read_text(encoding="utf-8")
    css = (STATIC / "pin.css").read_text(encoding="utf-8")

    def test_no_cdn_and_everything_self_hosted(self):
        for text in (self.html, self.js, self.css):
            for cdn in ("cdn", "unpkg", "jsdelivr", "googleapis", "gstatic", "cloudflare"):
                self.assertNotIn(cdn, text.lower())
        for ref in re.findall(r'<(?:script|link)[^>]+(?:src|href)="([^"]+)"', self.html):
            # "data:," is the empty favicon: it stops the browser fetching /favicon.ico
            self.assertTrue(ref.startswith("/static/") or ref == "data:,", ref)
        self.assertTrue((STATIC / "vendor/leaflet/leaflet.js").exists())
        self.assertTrue((STATIC / "vendor/leaflet/LICENSE").exists())
        self.assertIn('imagePath = "/static/vendor/leaflet/images/"', self.js)
        hosts = set(re.findall(r"https://([^/\"']+)", self.js))
        self.assertEqual(hosts, {"tile.openstreetmap.org", "www.openstreetmap.org"})

    def test_no_inline_script_style_or_handlers(self):
        for body in re.findall(r"<script([^>]*)>(.*?)</script>", self.html, re.S):
            self.assertIn("src=", body[0])
            self.assertEqual(body[1].strip(), "")
        self.assertNotIn("<style", self.html)
        self.assertIsNone(re.search(r"\sstyle\s*=", self.html))
        self.assertIsNone(re.search(r"\son[a-z]+\s*=", self.html))
        self.assertNotIn(".style", self.js)
        self.assertNotIn("setAttribute(\"style\"", self.js)
        self.assertNotIn("javascript:", self.html + self.js)

    def test_no_storage_tracking_or_html_injection(self):
        for banned in ("document.cookie", "localStorage", "sessionStorage", "indexedDB", "innerHTML",
                       "outerHTML", "insertAdjacentHTML", "document.write", "watchPosition", "eval("):
            self.assertNotIn(banned, self.js, banned)
            self.assertNotIn(banned, self.html, banned)

    def test_phone_location_only_inside_the_button_handler(self):
        self.assertEqual(self.js.count("getCurrentPosition"), 1)
        handler = self.js.index('el.gps.addEventListener("click"')
        use = self.js.index("getCurrentPosition")
        end = self.js.index("});", handler)
        self.assertTrue(handler < use < end, "geolocation must only be requested in the click handler")

    def test_page_copy(self):
        for text in ("Where is the problem?", "Use my phone's location (optional)", "Confirm location",
                     "Reply to our text with the road name instead", "OpenStreetMap", "Open Government Licence",
                     'role="status"', 'aria-live="polite"', 'for="pc"', 'href="/privacy"', 'id="submitBtn"'):
            self.assertIn(text, self.html)
        self.assertRegex(self.html, r'id="submitBtn"[^>]*disabled')

    def test_no_em_dashes_in_user_facing_text(self):
        texts = [self.html, self.js, pin_service.privacy_html(), *pin_service.MSG.values()]
        for text in texts:
            self.assertNotIn("—", text)


class BotAndPages(PinCase):
    def test_bot_endpoint(self):
        token = self.link("R-0074")
        self.post("/api/confirm", token=token, lat=INSIDE[0], lng=INSIDE[1])
        self.assertEqual(self.client.get("/api/location/R-0074").status_code, 404, "off without BOT_API_KEY")
        os.environ["BOT_API_KEY"] = "s3cret-key"
        self.assertEqual(self.client.get("/api/location/R-0074").status_code, 401)
        self.assertEqual(self.client.get("/api/location/R-0074", headers={"X-Api-Key": "wrong"}).status_code, 401)
        r = self.client.get("/api/location/R-0074", headers={"X-Api-Key": "s3cret-key"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["location"]["street"], "Windsor Terrace")
        self.assertEqual(r.get_json()["location_text"], "Windsor Terrace, near The Bargate, SO14 7BQ")
        self.assertEqual(self.client.get("/api/location/R-9999", headers={"X-Api-Key": "s3cret-key"}).status_code, 404)
        self.assertEqual(self.client.get("/api/location/R%3B1", headers={"X-Api-Key": "s3cret-key"}).status_code, 400)

    def test_privacy_page(self):
        page = self.client.get("/privacy").get_data(as_text=True)
        self.assertIn("[set CONTROLLER_NAME]", page)
        self.assertIn("[set CONTACT_EMAIL]", page)
        os.environ["CONTROLLER_NAME"] = "Kerbside team <test>"
        os.environ["CONTACT_EMAIL"] = "privacy@example.org"
        page = self.client.get("/privacy").get_data(as_text=True)
        self.assertIn("Kerbside team &lt;test&gt;", page)
        self.assertIn("privacy@example.org", page)
        for must in ("OpenStreetMap", "postcodes.io", "ico.org.uk"):
            self.assertIn(must, page)

    def test_demo_only_when_enabled(self):
        self.assertEqual(self.client.get("/demo").status_code, 404)
        os.environ["DEMO"] = "1"
        r = self.client.get("/demo")
        self.assertEqual(r.status_code, 302)
        self.assertRegex(r.headers["Location"], r"/p/[A-Za-z0-9_-]+$")


class Geocoder(unittest.TestCase):
    def test_busy_lock_skips_street_instead_of_waiting(self):
        class BusyLock:
            def acquire(self, timeout):
                return False

            def release(self):
                raise AssertionError("never acquired")

        g = pin_service.ReverseGeocoder()
        g.lock = BusyLock()
        with unittest.mock.patch.object(pin_service, "_http_get_json") as http:
            self.assertIsNone(g.lookup(*INSIDE))
            http.assert_not_called()

    def test_cache_by_rounded_coordinate(self):
        g = pin_service.ReverseGeocoder()
        g.lock = FreeLock()
        web = FakeWeb()
        with unittest.mock.patch.object(pin_service, "_http_get_json", web):
            g.lookup(50.906901, -1.405801)
            g.lookup(50.906904, -1.405804)
        self.assertEqual(len(web.calls), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)

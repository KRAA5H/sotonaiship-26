"""The four agent tools, as plain functions plus OpenAI-style tool schemas.

  find_category_facts  rules and verified facts for one category
  check_duplicate      open report, same category, same location text, within 30 days
  save_report          one row in reports; returns the resident's private link
  get_report_status    looked up by link_token only, never by report id

Every tool returns a dict with "ok". Errors come back as {"ok": False, "error"}
so the model can read them and recover, rather than the relay crashing.
The relay calls call_tool(name, arguments) with whatever the model sent.
"""

import hashlib
import hmac
import json
import os
import re
import secrets
import sys
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import reports_db
from location import LocationService

AGENT_DIR = reports_db.ROOT / "agent"
sys.path.insert(0, str(AGENT_DIR))

import loader  # noqa: E402  (agent/loader.py)

SITE_URL = (os.getenv("SITE_URL") or "http://localhost:5005").rstrip("/")
SEVERITIES = ("high", "medium", "low")
STATUS_TEXT = {
    "new": "logged here, not looked at yet",
    "in_review": "in review on this dashboard",
    "resolved": "marked as resolved here",
}
# Our own labels and synthetic phrases: never shown to a resident as fact.
_HIDDEN_CATEGORY_FIELDS = {"team", "team_confirmed", "example_phrases", "fms_categories"}

# One shared instance: geocoding is rate-limited to 1 request/second inside
# LocationService itself, so every caller in this process should go through
# the same object rather than creating a fresh one per call.
_location_service = LocationService()


@lru_cache(maxsize=1)
def _rulebook():
    categories, facts = loader.load(AGENT_DIR)
    raw = json.loads((AGENT_DIR / "categories.json").read_text(encoding="utf-8"))
    return categories, facts, raw


def category_ids():
    return list(_rulebook()[0])


def category_labels():
    return {cid: c["label"] for cid, c in _rulebook()[0].items()}


def _now():
    return datetime.now(timezone.utc)


def _normalise_location(text):
    """'12  Portswood Rd.' and '12 portswood rd' compare equal."""
    text = re.sub(r"[^\w\s]", " ", (text or "").lower())
    return " ".join(text.split())


_DIRECTIONS = ("north", "south", "east", "west", "upper", "lower")


def _same_place(one, other):
    """Same street, allowing one to carry extra words.

    The resident who writes "Weston Lane" and the one who writes "weston lane
    outside the school" are reporting the same place. A directional suffix is a
    different road, so "Weston Lane North" never matches "Weston Lane".
    """
    if one == other:
        return True
    short, long = (one, other) if len(one) <= len(other) else (other, one)
    if len(short) < 5 or f" {short} " not in f" {long} ":
        return False
    extra = long.replace(short, " ", 1).split()
    return not any(word in _DIRECTIONS for word in extra)


def _reporter_ref(reporter):
    """Salted hash of the sender handle. The raw number or email is never stored."""
    if not reporter:
        return None
    salt = (os.getenv("REPORTER_SALT") or "kerbside-dev-salt").encode()
    digest = hmac.new(salt, reporter.strip().lower().encode(), hashlib.sha256)
    return "h-" + digest.hexdigest()[:16]


def reporter_ref(reporter):
    """Public name for the salted sender hash, for the bot's status lookup."""
    return _reporter_ref(reporter)


def _with_conn(conn, work):
    if conn is not None:
        return work(conn)
    own = reports_db.connect()
    try:
        return work(own)
    finally:
        own.close()


# ---------------------------------------------------------------------------
# find_category_facts
# ---------------------------------------------------------------------------
def find_category_facts(category_id):
    categories, facts, raw = _rulebook()
    if category_id != "general" and category_id not in categories:
        return {"ok": False, "error": f"unknown category_id: {category_id}",
                "valid_ids": ["general", *categories]}

    result = {
        "ok": True,
        "facts": [
            {
                "topic": row["topic"],
                "fact": row["confirmed_fact"],
                "source_name": row["source_name"],
                "url": row["url"],
                "date_checked": row["date_checked"],
                "caveat": row["caveat"],
            }
            for row in facts.get(category_id, [])
        ],
    }
    if category_id == "general":
        return result

    category = categories[category_id]
    outcome = category["outcome"]
    result["category"] = {k: v for k, v in category.items() if k not in _HIDDEN_CATEGORY_FIELDS}
    result["outcome_rule"] = raw["outcomes"][outcome]
    if outcome == "council_report":
        result["location_rule"] = raw["location_check"]["rule"]
    else:
        result["guidance_links"] = raw["guidance_links"]
    return result


# ---------------------------------------------------------------------------
# check_duplicate
# ---------------------------------------------------------------------------
# Placeholders saved while we wait for a street. Two of them are never the same place.
MISSING_LOCATIONS = ("", "not given")
# Never saved, whatever the caller says. These are the rules, not the old gate:
# outside the city, a trunk road we cannot route, and a utility's problem.
NEVER_SAVED = {"outside_southampton", "not_council_trunk_road", "not_council_utility"}


def duplicate_rule():
    """The rule in categories.json: same category, same location text, open, within N days."""
    return _rulebook()[2]["meta"]["duplicate_rule"]["default"]


def duplicate_window_days(category_id):
    """The category agent's own window (fly-tipping 7 days, pothole 30...), else the default."""
    agent = (_rulebook()[0].get(category_id) or {}).get("agent") or {}
    days = agent.get("dup_window_days")
    return days if isinstance(days, (int, float)) and days > 0 else duplicate_rule()["window_days"]


def check_duplicate(category_id, location, conn=None, now=None):
    if not location or not location.strip():
        return {"ok": False, "error": "location is required"}
    rule = duplicate_rule()
    since = (now or _now()) - timedelta(days=duplicate_window_days(category_id))
    wanted = _normalise_location(location)
    statuses = rule["open_statuses_only"]
    if wanted in MISSING_LOCATIONS:
        # Never match on a missing street: two reports waiting for a location are
        # not the same problem just because neither has one yet.
        return {"ok": True, "is_duplicate": False, "duplicate_of": None, "matching_reports": 0}

    def work(c):
        # Resolved reports never count: a problem back after a repair is a new report.
        rows = c.execute(
            "SELECT id, created_at, location, duplicate_of FROM reports "
            f"WHERE category_id = ? AND status IN ({', '.join('?' * len(statuses))}) "
            "ORDER BY created_at",
            (category_id, *statuses),
        ).fetchall()
        matches = [
            r for r in rows
            if _normalise_location(r["location"]) not in MISSING_LOCATIONS
            and _same_place(_normalise_location(r["location"]), wanted)
            and datetime.fromisoformat(r["created_at"]) >= since
        ]
        if not matches:
            return {"ok": True, "is_duplicate": False, "duplicate_of": None, "matching_reports": 0}
        first = matches[0]
        return {
            "ok": True,
            "is_duplicate": True,
            # Point at the original, even if the earliest match is itself a repeat.
            "duplicate_of": first["duplicate_of"] or first["id"],
            "matching_reports": len(matches),
        }

    return _with_conn(conn, work)


# ---------------------------------------------------------------------------
# save_report
# ---------------------------------------------------------------------------
def local_area(location):
    """The area a Southampton street is in, from the offline street list, or None."""
    try:
        from geo import southampton as city  # noqa: PLC0415
    except ImportError:
        return None
    rows = city.street_in_text(location or "")
    if not rows:
        return None
    if len(rows) == 1:
        return rows[0]["area"] or None
    named = city.area_in_text(rows, location)
    return named["area"] if named else None


def save_report(category_id, location, description, severity=None, has_photo=False,
                reporter=None, conn=None, area=None):
    categories = _rulebook()[0]
    if category_id not in categories:
        return {"ok": False, "error": f"unknown category_id: {category_id}"}
    if category_id in NEVER_SAVED:
        return {"ok": False, "error": f"{category_id} is never saved: point the resident to "
                                      "official guidance instead"}
    if not (description or "").strip():
        return {"ok": False, "error": "description is required"}
    if severity is not None and severity not in SEVERITIES:
        return {"ok": False, "error": f"severity must be one of {', '.join(SEVERITIES)}"}
    # Capture-first: the caller decides whether the evidence is kept (triage.normalise,
    # and later the graph policy). A missing street is the truthful state, not a reason
    # to discard a real report. The placeholder never matches a duplicate.
    place = (location or "").strip() or "Not given"

    # Geocode BEFORE opening the transaction - this is a network call, and
    # holding BEGIN IMMEDIATE (a write lock on the whole file) while waiting
    # on Nominatim would block every other writer for no reason. If the
    # lookup fails or finds nothing, area stays None - never block saving
    # the report itself on a geocoding miss.
    #
    # TEST NOTE: this is a real network call. test_website.py calls
    # save_report() directly and does not mock this - add
    # `unittest.mock.patch.object(tools._location_service, "forward_geocode",
    # return_value=None)` to its setUp (see the updated test_website.py)
    # so the test suite stays network-free, matching every other test file
    # in this repo.
    #
    # Speed: the location agent usually knows the area already (it is passed
    # in), and the offline street list knows it for any Southampton street.
    # Nominatim is only asked when neither does, and never for the "Not given"
    # placeholder, which no geocoder can place.
    if area is None:
        area = local_area(place)
    if area is None and place.lower() not in MISSING_LOCATIONS:
        try:
            geocoded = _location_service.forward_geocode(place)
            if geocoded:
                area = geocoded.get("area")
        except Exception as error:  # noqa: BLE001 - geocoding must never block a save
            print(f"[geocode] forward_geocode failed for {place!r}: {error}")

    def work(c):
        # IMMEDIATE takes the write lock now, so two webhooks cannot pick the same id.
        c.execute("BEGIN IMMEDIATE")
        try:
            duplicate = check_duplicate(category_id, place, conn=c)
            last = c.execute(
                "SELECT MAX(CAST(SUBSTR(id, 3) AS INTEGER)) FROM reports WHERE id LIKE 'R-%'"
            ).fetchone()[0]
            report_id = f"R-{(last or 0) + 1:04d}"
            link_token = secrets.token_urlsafe(12)
            c.execute(
                "INSERT INTO reports (id, created_at, category_id, status, severity, location, "
                "area, description, has_photo, duplicate_of, reporter_ref, link_token) "
                "VALUES (?, ?, ?, 'new', ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    report_id,
                    _now().isoformat(timespec="seconds"),
                    category_id,
                    severity,
                    place,
                    area,
                    description.strip(),
                    int(bool(has_photo)),
                    duplicate["duplicate_of"],
                    _reporter_ref(reporter),
                    link_token,
                ),
            )
            c.execute("COMMIT")
        except Exception:
            c.execute("ROLLBACK")
            raise
        return {
            "ok": True,
            "report_id": report_id,  # internal: never put this in a resident link
            "link_token": link_token,
            "link": f"{SITE_URL}/r/{link_token}",
            "area": area,
            "duplicate_of": duplicate["duplicate_of"],
            "matching_reports": duplicate["matching_reports"],
        }

    return _with_conn(conn, work)


# ---------------------------------------------------------------------------
# get_report_status
# ---------------------------------------------------------------------------
def get_report_status(link_token, conn=None):
    if not isinstance(link_token, str) or not 8 <= len(link_token) <= 64:
        return {"ok": False, "error": "no report found for that link"}

    def work(c):
        row = c.execute(
            "SELECT created_at, category_id, status, location, area, description, has_photo, "
            "photo_guid, photo_mime, duplicate_of FROM reports WHERE link_token = ?",
            (link_token,),
        ).fetchone()
        if row is None:
            return {"ok": False, "error": "no report found for that link"}
        category = _rulebook()[0].get(row["category_id"], {})
        # Only what the resident already told us, plus status. No id, no reporter_ref.
        return {
            "ok": True,
            "status": row["status"],
            "status_text": STATUS_TEXT.get(row["status"], row["status"]),
            "category": category.get("label", row["category_id"]),
            "location": row["location"],
            "area": row["area"],
            "description": row["description"],
            "created_at": row["created_at"],
            "has_photo": bool(row["has_photo"]),
            "photo_url": (f"/r/{link_token}/photo"
                          if row["photo_guid"] and row["photo_mime"] in ("image/jpeg", "image/png")
                          else None),
            "reported_by_others_too": bool(row["duplicate_of"]),
        }

    return _with_conn(conn, work)


# ---------------------------------------------------------------------------
# Tool schemas (OpenAI-compatible, matching llm.py) and the dispatcher
# ---------------------------------------------------------------------------
def tool_schemas():
    ids = category_ids()
    return [
        {"type": "function", "function": {
            "name": "find_category_facts",
            "description": "Get the rules, follow-up questions, official form link and verified facts "
                           "(with source URL and date checked) for one category. Use 'general' for "
                           "facts about the council itself. Only state facts this tool returns.",
            "parameters": {"type": "object", "required": ["category_id"], "properties": {
                "category_id": {"type": "string", "enum": ["general", *ids]},
            }},
        }},
        {"type": "function", "function": {
            "name": "check_duplicate",
            "description": "Check whether the same problem is already open (not resolved) at the "
                           "same location, reported in the last 30 days.",
            "parameters": {"type": "object", "required": ["category_id", "location"], "properties": {
                "category_id": {"type": "string", "enum": ids},
                "location": {"type": "string", "description": "where the problem is"},
            }},
        }},
        {"type": "function", "function": {
            "name": "save_report",
            "description": "Save one council report once the follow-up questions are answered. "
                           "Only for council_report categories. Returns the resident's private link.",
            "parameters": {"type": "object", "required": ["category_id", "location", "description"],
                           "properties": {
                "category_id": {"type": "string", "enum": ids},
                "location": {"type": "string", "description": "where the problem is, as the resident said it"},
                "description": {"type": "string", "description": "what is wrong, in one or two sentences"},
                "severity": {"type": "string", "enum": list(SEVERITIES)},
                "has_photo": {"type": "boolean"},
            }},
        }},
        {"type": "function", "function": {
            "name": "get_report_status",
            "description": "Look up a report's status from the token in the resident's private link.",
            "parameters": {"type": "object", "required": ["link_token"], "properties": {
                "link_token": {"type": "string"},
            }},
        }},
    ]


TOOLS = {
    "find_category_facts": find_category_facts,
    "check_duplicate": check_duplicate,
    "save_report": save_report,
    "get_report_status": get_report_status,
}
# Arguments the model may set. reporter is passed by the relay, never the model.
_MODEL_ARGS = {
    s["function"]["name"]: set(s["function"]["parameters"]["properties"]) for s in tool_schemas()
}


def call_tool(name, arguments, reporter=None):
    """Run one tool call from the model. arguments may be a JSON string or a dict."""
    if name not in TOOLS:
        return {"ok": False, "error": f"unknown tool: {name}"}
    try:
        args = json.loads(arguments) if isinstance(arguments, str) else dict(arguments or {})
    except (json.JSONDecodeError, TypeError, ValueError):
        return {"ok": False, "error": "arguments were not valid JSON"}
    unexpected = set(args) - _MODEL_ARGS[name]
    if unexpected:
        return {"ok": False, "error": f"unexpected arguments: {', '.join(sorted(unexpected))}"}
    if name == "save_report":
        args["reporter"] = reporter
    try:
        return TOOLS[name](**args)
    except TypeError as error:
        return {"ok": False, "error": f"bad arguments: {error}"}

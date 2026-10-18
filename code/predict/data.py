"""The read-only link to the live complaints, and the distinct-problem counts.

kerbside.db is opened with mode=ro, so a long query can never block or change
the bot. A distinct problem is a root report plus its duplicates, counted once;
"noticed" keeps how many people reported it. Locations become one street key
through the city gazetteer, so "weston lane" and "Weston Ln" are one street.
Only these columns are read: never description, reporter_ref or link_token.
"""

import json
import re
import sqlite3
import sys
import time
from datetime import date, datetime, timedelta, timezone

from . import config

sys.path.insert(0, str(config.CODE))
from geo import southampton as geo  # noqa: E402

COLUMNS = ("id", "created_at", "category_id", "status", "severity", "location", "area",
           "duplicate_of", "status_changed_at", "photo_features")
MISSING = {"", "not given", "unknown", "none"}
STREETISH = re.compile(
    r"([a-z][a-z' ]*?\s(?:road|street|lane|avenue|close|drive|way|crescent|terrace|place|gardens|"
    r"grove|hill|square|parade|walk|court|row|valley|high street))\b", re.I)


class Unavailable(Exception):
    """The live database could not be read; callers fall back to the last saved run."""


def connect_ro(path=None, tries=3):
    path = path or config.KERBSIDE_DB
    if not path.exists():
        raise Unavailable(f"{path.name} not found")
    for attempt in range(tries):
        try:
            conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=2)
            conn.row_factory = sqlite3.Row
            conn.execute("SELECT 1 FROM reports LIMIT 1")
            return conn
        except sqlite3.OperationalError as error:
            if attempt == tries - 1:
                raise Unavailable(str(error)) from error
            time.sleep(0.5)


def _fake_ids():
    try:
        return {r["id"] for r in json.loads(config.FAKE_REPORTS.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return set()


def parse_time(value):
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def street_key(location, area=None):
    """(street, area) for free text, or (None, area) when no city street is named."""
    text = (location or "").strip()
    if text.lower() in MISSING:
        return None, area or None
    rows = geo.street_in_text(text)
    named = STREETISH.search(text)
    if rows and named:
        # "Old Northam Road" must not become the gazetteer's "Northam Road".
        written, found = geo.normalise(named.group(1)), geo.normalise(rows[0]["street"])
        if written != found and written.endswith(" " + found):
            return named.group(1).title(), area or None
    if not rows:
        # Not in the gazetteer (it misses some streets, e.g. Old Northam Road):
        # keep the named street, without the house number, so it still counts.
        named = STREETISH.search(text)
        return (named.group(1).title(), area or None) if named else (None, area or None)
    chosen = geo.area_in_text(rows, text) or next((r for r in rows if area and r["area"] == area), rows[0])
    return chosen["street"], chosen["area"] or area or None


def _hazard(raw):
    try:
        return (json.loads(raw or "{}") or {}).get("hazard") == "yes"
    except (TypeError, ValueError):
        return False


def load_live(path=None, since=None):
    """Reports from the bot's database as plain dicts, oldest first."""
    conn = connect_ro(path)
    try:
        have = {r["name"] for r in conn.execute("PRAGMA table_info(reports)")}
        cols = [c for c in COLUMNS if c in have]
        sql = f"SELECT {', '.join(cols)} FROM reports"
        args = ()
        if since:
            sql += " WHERE created_at > ?"
            args = (since,)
        rows = [dict(r) for r in conn.execute(sql + " ORDER BY created_at, id", args)]
    finally:
        conn.close()
    fake = _fake_ids()
    for row in rows:
        row["synthetic"] = 1 if row["id"] in fake else 0
        row.setdefault("area", None)
    return rows


def distinct_problems(rows):
    """One record per problem: root reports only, with how many people noticed it."""
    noticed = {}
    for row in rows:
        if row.get("duplicate_of"):
            noticed[row["duplicate_of"]] = noticed.get(row["duplicate_of"], 0) + 1
    problems = []
    for row in rows:
        if row.get("duplicate_of"):
            continue
        when = parse_time(row.get("created_at"))
        if when is None:
            continue
        street, area = street_key(row.get("location"), row.get("area"))
        problems.append({
            "id": row["id"], "at": when, "day": when.date(), "category": row["category_id"],
            "street": street, "area": area, "severity": row.get("severity"),
            "hazard": _hazard(row.get("photo_features")), "status": row.get("status"),
            "noticed": 1 + noticed.get(row["id"], 0), "synthetic": int(row.get("synthetic", 0)),
        })
    return problems


def week_start(day):
    """Monday of the week containing day."""
    if isinstance(day, datetime):
        day = day.date()
    return day - timedelta(days=day.weekday())


def today():
    return datetime.now(timezone.utc).date()


def next_week_start(day=None):
    return week_start(day or today()) + timedelta(days=7)


def as_date(value):
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])

"""Load recent public FixMyStreet reports for Southampton into kerbside.db.

Source: FixMyStreet's official Open311 API (mySociety / SocietyWorks), the
machine-readable form of https://www.fixmystreet.com/reports/Southampton.
Report data: mySociety FixMyStreet (ODC-BY). Permission: DECISIONS.md.

Politeness (https://www.fixmystreet.com/robots.txt asks for Crawl-delay: 3):
  - one Open311 request for the most recent LIMIT reports, cached; a cached
    response is never requested again
  - never fetch /photo/ (disallowed): a photo is kept as yes/no only
  - street names come from OpenStreetMap Nominatim, at most one request a
    second, cached by coordinate, so each point is looked up once
  - a user agent that names the project and links to the repo

What is kept per report: created date, category, a one-line description (the
report's title), the street, status, has_photo yes/no, and the report URL
(source_url, internal only). No names, emails, usernames or coordinates.

Run:
  python code/import_fixmystreet.py           fetch what is not cached, add new reports
  python code/import_fixmystreet.py --reset   rebuild kerbside.db from the cache only, no network
"""

import argparse
import json
import re
import secrets
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import reports_db  # noqa: E402
import tools  # noqa: E402
from geo import southampton as city  # noqa: E402

CACHE = HERE / "data" / "fixmystreet_cache"          # gitignored
REPORTS_CACHE = CACHE / "open311_recent.json"
GEOCODE_CACHE = CACHE / "geocode.json"

OPEN311 = "https://www.fixmystreet.com/open311/v2/requests.json"
NOMINATIM = "https://nominatim.openstreetmap.org/reverse"
SOUTHAMPTON = "2567"     # MapIt area id for Southampton City Council
LIMIT = 150
USER_AGENT = "KerbsideImport/0.1 (SotonShip 2026 hackathon; +https://github.com/KRAA5H/sotonaiship-26)"
GEOCODE_DELAY = 1.1      # Nominatim allows one request a second

# FixMyStreet category -> our category_id (agent/categories.json). Only clean
# matches are listed. Everything else is stored as "unclear_other", which the
# dashboard labels "Unclear or other": traffic lights, signs, trees, pavements
# and the rest are real council work our categories do not cover, and we do not
# force-fit them.
CATEGORY_MAP = {
    "Potholes": "pothole",
    "Flytipping": "fly_tipping",
    "Litter in the street": "litter_street_cleaning",
    "Street cleaning": "litter_street_cleaning",
    "Graffiti": "graffiti_flyposting",
    "Flyposting": "graffiti_flyposting",
    "Dog fouling": "dog_fouling",
    "Dead animals": "dead_animal",
    "Illegal parking": "illegal_parking",
}
UNMAPPED = "unclear_other"
# Not imported. D48: problems at one neighbour's home go to the council's own
# form and are never saved here, so a public report about a home is not either.
SKIPPED_CATEGORIES = {"Noise nuisance", "Rubbish accumulation on private property"}

# FixMyStreet's Open311 feed gives only "open" or "closed".
#   open   -> new       (FixMyStreet's finer states such as "investigating"
#                        are not in the feed, so nothing becomes in_review)
#   closed -> resolved  (fixed, or closed by the council)
STATUS_MAP = {"open": "new", "closed": "resolved"}

# House numbers in a title ("outside 31 Cambridge Road", "Alma 54") are dropped: street level only.
HOUSE_NUMBER = re.compile(r"\b\d+[a-zA-Z]?\s*(?=[A-Z][a-z]+)")
NUMBER_AFTER_NAME = re.compile(r"\b([A-Z][a-z]+)\s+\d+[a-zA-Z]?\b")


def _get_json(url, accept="application/json"):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def fetch_reports():
    """The most recent LIMIT reports, from the cache if we already have them."""
    if REPORTS_CACHE.exists():
        return json.loads(REPORTS_CACHE.read_text(encoding="utf-8"))["service_requests"]
    params = {"jurisdiction_id": "fixmystreet", "agency_responsible": SOUTHAMPTON, "max_requests": str(LIMIT)}
    url = f"{OPEN311}?{urllib.parse.urlencode(params)}"
    items = _get_json(url)["service_requests"][:LIMIT]
    CACHE.mkdir(parents=True, exist_ok=True)
    REPORTS_CACHE.write_text(json.dumps({
        "source": "FixMyStreet Open311 API (mySociety / SocietyWorks), ODC-BY",
        "url": url, "user_agent": USER_AGENT,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "service_requests": items,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    return items


def _load_geocode_cache():
    if GEOCODE_CACHE.exists():
        return json.loads(GEOCODE_CACHE.read_text(encoding="utf-8"))
    return {}


def street_for(report, cache, offline):
    """Road name for the report's point. Cached; offline mode never asks Nominatim."""
    key = f"{float(report['lat']):.5f},{float(report['long']):.5f}"
    if key not in cache:
        if offline:
            return ""
        time.sleep(GEOCODE_DELAY)
        params = urllib.parse.urlencode({"lat": report["lat"], "lon": report["long"], "format": "jsonv2",
                                         "zoom": "17", "addressdetails": "1"})
        address = _get_json(f"{NOMINATIM}?{params}").get("address", {})
        cache[key] = address.get("road") or address.get("pedestrian") or address.get("footway") or ""
        GEOCODE_CACHE.write_text(json.dumps(cache, indent=1), encoding="utf-8")
    return cache[key]


def area_for(street, lat, lng):
    """Named area of the nearest gazetteer entry with this street name, or None."""
    wanted = city.normalise(street)
    rows = [r for r in city._streets() if r[4] == wanted] if wanted else []
    if not rows:
        return None
    nearest = min(rows, key=lambda r: (r[2] - lat) ** 2 + (r[3] - lng) ** 2)
    return nearest[1] or None


def one_line(title):
    text = " ".join((title or "").split())
    text = NUMBER_AFTER_NAME.sub(r"\1", HOUSE_NUMBER.sub("", text))
    text = " ".join(text.split())
    return text[:117] + "..." if len(text) > 120 else text


def to_row(report, street):
    created = datetime.fromisoformat(report["requested_datetime"]).astimezone(timezone.utc)
    lat, lng = float(report["lat"]), float(report["long"])
    return {
        "created_at": created.isoformat(timespec="seconds"),
        "category_id": CATEGORY_MAP.get(report.get("service_name"), UNMAPPED),
        "status": STATUS_MAP.get(report.get("status"), "new"),
        # The report went to the council through FixMyStreet.
        "capture_state": "submitted",
        "routing_status": "verified",
        "severity": None,           # FixMyStreet has no severity; we do not invent one
        "location": street or None,
        "area": area_for(street, lat, lng) if street else None,
        "description": one_line(report.get("title") or report.get("service_name")),
        "has_photo": int(bool(report.get("media_url"))),
        "reporter_ref": None,
        "link_token": secrets.token_urlsafe(12),
        "source": "fixmystreet",
        "source_url": f"https://www.fixmystreet.com/report/{report['service_request_id']}",
    }


def import_reports(conn, reports, offline):
    """Insert reports not already in the database, oldest first, so the
    duplicate rule only ever looks back in time. Returns counts."""
    cache = _load_geocode_cache()
    known = {r[0] for r in conn.execute("SELECT source_url FROM reports WHERE source_url IS NOT NULL")}
    counts = {"imported": 0, "skipped_category": 0, "already_present": 0, "no_street": 0, "categories": {}}
    for report in sorted(reports, key=lambda r: r["requested_datetime"]):
        if report.get("service_name") in SKIPPED_CATEGORIES:
            counts["skipped_category"] += 1
            continue
        url = f"https://www.fixmystreet.com/report/{report['service_request_id']}"
        if url in known:
            counts["already_present"] += 1
            continue
        row = to_row(report, street_for(report, cache, offline))
        if not row["location"]:
            counts["no_street"] += 1
        else:
            # Our duplicate rule (tools.check_duplicate): same category, same
            # street, open reports only, within the window, as of this report's date.
            found = tools.check_duplicate(row["category_id"], row["location"], conn=conn,
                                          now=datetime.fromisoformat(row["created_at"]))
            row["duplicate_of"] = found.get("duplicate_of")
        last = conn.execute(
            "SELECT MAX(CAST(SUBSTR(id, 3) AS INTEGER)) FROM reports WHERE id LIKE 'R-%'").fetchone()[0]
        row["id"] = f"R-{(last or 0) + 1:04d}"
        columns = ", ".join(row)
        conn.execute(f"INSERT INTO reports ({columns}) VALUES ({', '.join('?' * len(row))})", tuple(row.values()))
        counts["imported"] += 1
        counts["categories"][row["category_id"]] = counts["categories"].get(row["category_id"], 0) + 1
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--reset", action="store_true",
                        help="delete kerbside.db and rebuild it from the cache, with no network")
    args = parser.parse_args()

    if args.reset:
        if not REPORTS_CACHE.exists():
            sys.exit(f"No cache at {REPORTS_CACHE}. Run once without --reset to fetch it.")
        for suffix in ("", "-wal", "-shm"):
            Path(str(reports_db.DB_PATH) + suffix).unlink(missing_ok=True)
    reports = fetch_reports()
    reports_db.init_db()
    conn = reports_db.connect()
    try:
        counts = import_reports(conn, reports, offline=args.reset)
    finally:
        conn.close()
    print(f"{reports_db.DB_PATH}: {len(reports)} in the feed, {counts['imported']} imported, "
          f"{counts['already_present']} already present, {counts['skipped_category']} skipped (D48), "
          f"{counts['no_street']} without a street")
    for category, n in sorted(counts["categories"].items(), key=lambda kv: kv[0]):
        print(f"  {category}: {n}")


if __name__ == "__main__":
    main()

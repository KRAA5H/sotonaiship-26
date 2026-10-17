"""Collect real Southampton reports from FixMyStreet's official Open311 API.

Used only by the evaluation. Nothing here goes into kerbside.db or the
dashboard. Everything downloaded lands in code/eval/fms/raw/, which is
gitignored because the repo may go public.

Politeness, from https://www.fixmystreet.com/robots.txt and /open311:
  - one request at a time, at least CRAWL_DELAY seconds apart (robots asks 3)
  - never fetch /photo/ (disallowed by robots.txt), so media_url is not followed
  - at most WINDOWS requests of up to 1000 reports (the site's max_requests)
  - a user agent that names the project and links to the repo

Run:
  python code/eval/fms/collect.py
"""

import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
BASE = "https://www.fixmystreet.com/open311/v2/requests.json"
# MapIt area id for Southampton City Council. Checked 2026-10-17: every
# returned request lists "Southampton City Council" as the recipient.
SOUTHAMPTON = "2567"
USER_AGENT = "KerbsideEval/0.1 (SotonShip 2026 hackathon evaluation; +https://github.com/KRAA5H/sotonaiship-26)"
CRAWL_DELAY = 5
WINDOWS = 3


def fetch(end_date=None):
    params = {"jurisdiction_id": "fixmystreet", "agency_responsible": SOUTHAMPTON, "max_requests": "1000"}
    if end_date:
        params["end_date"] = end_date
    url = f"{BASE}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return url, json.load(response)["service_requests"]


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    seen, manifest, end_date = {}, [], None
    for window in range(WINDOWS):
        if window:
            time.sleep(CRAWL_DELAY)
        url, items = fetch(end_date)
        fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        new = [r for r in items if r["service_request_id"] not in seen]
        for report in new:
            seen[report["service_request_id"]] = report
        manifest.append({"url": url, "fetched_at": fetched_at, "returned": len(items), "new": len(new)})
        print(f"window {window + 1}: {len(items)} returned, {len(new)} new")
        if not new:
            break
        # Next window ends just before the oldest report we have.
        end_date = min(r["requested_datetime"] for r in new)

    reports = sorted(seen.values(), key=lambda r: r["requested_datetime"], reverse=True)
    (RAW / "reports.json").write_text(json.dumps(reports, ensure_ascii=False, indent=1), encoding="utf-8")
    (RAW / "manifest.json").write_text(json.dumps({
        "source": "FixMyStreet Open311 API (mySociety / SocietyWorks)",
        "user_agent": USER_AGENT,
        "requests": manifest,
        "total_reports": len(reports),
    }, indent=1), encoding="utf-8")
    print(f"{len(reports)} reports, {reports[-1]['requested_datetime'][:10]} to {reports[0]['requested_datetime'][:10]}")


if __name__ == "__main__":
    main()

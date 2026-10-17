"""Pick the evaluation set from the collected FixMyStreet reports and propose labels.

  60 reports for category accuracy
  20 likely repeats: same FixMyStreet category, under 30 m, under 14 days, ranked
     by wording overlap and repeat cues ("again", "still", "reported"), so the
     catch rate is measured on pairs that might really be the same problem
  20 same-street pairs (same FixMyStreet category, under 50 m, under 30 days),
     which on a hotspot street are often new incidents: the false-positive test
  20 hard negatives: 10 same street with a different issue, 10 same issue on a different street

The proposed category is only a starting point taken from categories.json's
fms_categories lists. Every label is then checked by hand before scoring.

Street names come from OpenStreetMap Nominatim (one request per second,
cached), because Open311 returns coordinates but no street. Only the reports
used in pairs are looked up.

Writes code/eval/fms/raw/proposed.json (gitignored: it holds report text).

Run:
  python code/eval/fms/select.py
"""

import json
import math
import random
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
ROOT = HERE.parent.parent.parent
sys.path.insert(0, str(ROOT / "agent"))
import loader  # noqa: E402

USER_AGENT = "KerbsideEval/0.1 (SotonShip 2026 hackathon evaluation; +https://github.com/KRAA5H/sotonaiship-26)"
SEED = 2026
STOPWORDS = set("the a an and of on in to is at for this there it has been by with near from are be as "
                "outside road street".split())
REPEAT_CUE = re.compile(r"(still|again|previous(ly)?|already|reported|same)")
RECENT_FROM = "2023-01-01"


def when(report):
    return datetime.fromisoformat(report["requested_datetime"])


def metres(a, b):
    lat_a, lat_b = float(a["lat"]), float(b["lat"])
    dx = (float(a["long"]) - float(b["long"])) * 111320 * math.cos(math.radians(lat_a))
    dy = (lat_a - lat_b) * 110540
    return math.hypot(dx, dy)


def words(report):
    text = (report.get("description") or "").lower()
    return {w for w in re.findall(r"[a-z]+", text) if len(w) > 2 and w not in STOPWORDS}


def repeat_score(a, b):
    """Wording overlap plus a bonus when the later report sounds like a repeat."""
    wa, wb = words(a), words(b)
    overlap = len(wa & wb) / max(1, len(wa | wb))
    return overlap + (0.3 if REPEAT_CUE.search((b.get("description") or "").lower()) else 0)


def proposed_category(service_name, fms_map):
    # FixMyStreet services the rulebook does not cover go to council_service_other.
    return fms_map.get(service_name, "council_service_other")


_cache_path = RAW / "geocode_cache.json"
_cache = json.loads(_cache_path.read_text(encoding="utf-8")) if _cache_path.exists() else {}


def street(report):
    """Road name for the report's point, from Nominatim. Cached by rounded coordinate."""
    key = f"{float(report['lat']):.5f},{float(report['long']):.5f}"
    if key not in _cache:
        time.sleep(1.1)
        params = urllib.parse.urlencode({"lat": report["lat"], "lon": report["long"], "format": "jsonv2",
                                         "zoom": "17", "addressdetails": "1"})
        request = urllib.request.Request(f"https://nominatim.openstreetmap.org/reverse?{params}",
                                         headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=30) as response:
            address = json.load(response).get("address", {})
        _cache[key] = address.get("road") or address.get("pedestrian") or address.get("footway") or ""
        _cache_path.write_text(json.dumps(_cache, indent=1), encoding="utf-8")
    return _cache[key]


def brief(report, fms_map):
    return {
        "fms_id": report["service_request_id"],
        "date": report["requested_datetime"][:10],
        "fms_category": report["service_name"],
        "proposed": proposed_category(report["service_name"], fms_map),
        "title": report.get("title", ""),
        "text": report.get("description", ""),
        "requestor_name": report.get("requestor_name"),
        "lat": report["lat"],
        "long": report["long"],
        "url": f"https://www.fixmystreet.com/report/{report['service_request_id']}",
    }


def main():
    categories, _ = loader.load(ROOT / "agent")
    fms_map = {}
    for cid, category in categories.items():
        for name in category.get("fms_categories", []):
            fms_map.setdefault(name, cid)

    reports = json.loads((RAW / "reports.json").read_text(encoding="utf-8"))
    rng = random.Random(SEED)

    # 60 for category accuracy: recent first, at most 6 per FixMyStreet category,
    # so the set covers close categories and services we do not handle.
    recent = [r for r in reports if r["requested_datetime"] >= RECENT_FROM]
    rng.shuffle(recent)
    per_service, picked = {}, []
    for r in recent:
        if per_service.get(r["service_name"], 0) < 6:
            per_service[r["service_name"]] = per_service.get(r["service_name"], 0) + 1
            picked.append(r)
        if len(picked) == 60:
            break
    used = {r["service_request_id"] for r in picked}

    pool = [r for r in reports if r["service_request_id"] not in used]
    pool.sort(key=when)
    same, diff_issue, diff_street, likely = [], [], [], []
    for i, a in enumerate(pool):
        for b in pool[i + 1:]:
            gap = (when(b) - when(a)).days
            if gap > 30:
                break
            d = metres(a, b)
            if a["service_name"] == b["service_name"] and d < 30 and gap <= 14:
                likely.append((a, b, d, gap))
            if a["service_name"] == b["service_name"] and d < 50:
                same.append((a, b, d, gap))
            elif a["service_name"] != b["service_name"] and d < 120:
                diff_issue.append((a, b, d, gap))
            elif a["service_name"] == b["service_name"] and d > 800:
                diff_street.append((a, b, d, gap))

    def take(candidates, n, shuffle=True):
        if shuffle:
            rng.shuffle(candidates)
        chosen, seen = [], set()
        for a, b, d, gap in candidates:
            ids = {a["service_request_id"], b["service_request_id"]}
            if ids & seen:
                continue
            seen |= ids
            chosen.append((a, b, d, gap))
            if len(chosen) == n:
                break
        return chosen

    def pair(a, b, d, gap, kind):
        return {"kind": kind, "metres": round(d), "days_apart": gap,
                "a": {**brief(a, fms_map), "street": street(a)},
                "b": {**brief(b, fms_map), "street": street(b)}}

    likely.sort(key=lambda p: (-repeat_score(p[0], p[1]), p[0]["service_request_id"], p[1]["service_request_id"]))
    repeats = [pair(*p, "likely_repeat") for p in take(likely, 20, shuffle=False)]
    pairs = [pair(*p, "same_street_same_issue") for p in take(same, 20)]
    negatives = ([pair(*p, "same_street_different_issue") for p in take(diff_issue, 10)]
                 + [pair(*p, "same_issue_different_street") for p in take(diff_street, 10)])

    out = {"reports": [brief(r, fms_map) for r in picked], "repeats": repeats, "pairs": pairs,
           "negatives": negatives}
    (RAW / "proposed.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(out['reports'])} reports, {len(repeats)} likely repeats, {len(pairs)} same-street pairs, "
          f"{len(negatives)} negatives")


if __name__ == "__main__":
    main()

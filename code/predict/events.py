"""Event calendar, coverage check and the event and season uplift table.

Events come from two places:
  data/events.csv           hand-entered rows, each with source_url and collected_on
  synthetic_events()        the SYNTHETIC calendar behind the synthetic history

Only confirmed events change a forecast at full strength; a proposed event is
shown as "possible" with low confidence. A venue outside the city boundary is
marked out_of_coverage and never creates a job (the Utilita Bowl case).
"""

import csv
import random
from datetime import date, timedelta

from . import config
from .data import geo

TYPES = ("match_day", "cruise_call", "university_move_out", "festival", "bank_holiday")
WINDOW_DAYS = {"match_day": 2, "cruise_call": 1, "university_move_out": 7, "festival": 2, "bank_holiday": 1}
UPLIFT_DAYS = 4            # day 0 to day 3 after the event
MIN_EVENTS = 5             # fewer past events than this: low confidence


def _venue_areas(venue):
    for key, areas in config.VENUE_AREAS.items():
        if key.lower() in (venue or "").lower():
            return tuple(areas)
    return ()


def coverage(event):
    """('inside', None) or ('outside', council) or ('unknown', None)."""
    lat, lng = event.get("lat"), event.get("lng")
    if lat is not None and lng is not None:
        inside = geo.in_city(lat, lng)
        if inside is False:
            return "outside", event.get("council") or "another council"
        if inside:
            return "inside", None
    if geo.names_outside_place(event.get("venue") or ""):
        return "outside", event.get("council") or "another council"
    return ("inside", None) if event.get("areas") else ("unknown", None)


def _float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def load_csv(path=None):
    path = path or config.EVENTS_CSV
    out = []
    try:
        with open(path, encoding="utf-8", newline="") as handle:
            for i, row in enumerate(csv.DictReader(handle)):
                if not row.get("start_date") or row.get("type") not in TYPES:
                    continue
                start = date.fromisoformat(row["start_date"])
                end = date.fromisoformat(row.get("end_date") or row["start_date"])
                event = {
                    "id": f"E-{i + 1:03d}", "name": row["name"], "type": row["type"], "start": start,
                    "end": end, "venue": row.get("venue", ""), "lat": _float(row.get("lat")),
                    "lng": _float(row.get("lng")), "size_tier": row.get("size_tier") or "unknown",
                    "source_url": row.get("source_url", ""), "collected_on": row.get("collected_on", ""),
                    "status": row.get("status") or "proposed", "synthetic": int(row.get("synthetic") or 0),
                    "council": row.get("council") or None, "areas": _venue_areas(row.get("venue")),
                }
                event["coverage"], event["outside_council"] = coverage(event)
                out.append(event)
    except OSError:
        pass
    return out


def synthetic_events(start, end, seed=config.SYNTH_SEED):
    """SYNTHETIC calendar: fortnightly Saturday matches out of season breaks, cruise calls
    April to October, and one move-out week at the end of June. Not real fixtures."""
    rng = random.Random(seed)
    out = []
    anchor = date(2026, 10, 24)             # a Saturday: keeps a match in the demo week
    day = anchor - timedelta(days=14 * ((anchor - start).days // 14))
    while day <= end:
        if day >= start and day.month not in (6, 7):
            out.append(("match_day", "Home match (synthetic)", "St Mary's Stadium", day, day, "large"))
        day += timedelta(days=14)
    day = start
    while day <= end:
        if 4 <= day.month <= 10 and day.weekday() in (2, 5) and rng.random() < 0.75:
            out.append(("cruise_call", "Cruise ship call (synthetic)", "Cruise terminals", day, day, "large"))
        if day.month == 6 and day.weekday() == 5 and (day + timedelta(days=7)).month == 7:
            out.append(("university_move_out", "Student move-out (synthetic)",
                        "University halls and student streets", day, day + timedelta(days=6), "large"))
        day += timedelta(days=1)
    events = []
    for i, (kind, name, venue, s, e, size) in enumerate(out):
        events.append({"id": f"SE-{i + 1:04d}", "name": name, "type": kind, "start": s, "end": e,
                       "venue": venue, "lat": None, "lng": None, "size_tier": size,
                       "source_url": "synthetic demo calendar", "collected_on": "", "status": "confirmed",
                       "synthetic": 1, "council": None, "areas": _venue_areas(venue),
                       "coverage": "inside", "outside_council": None})
    return events


def event_days(event):
    """Days the event affects demand: its own days plus the clean-up tail."""
    length = (event["end"] - event["start"]).days + WINDOW_DAYS.get(event["type"], 1)
    return [event["start"] + timedelta(days=i) for i in range(length)]


def weight(event):
    """Confirmed events count fully; proposed ones are only 'possible'."""
    return 1.0 if event.get("status") == "confirmed" else 0.3


# ---------------------------------------------------------------------------
# Uplift: extra problems in the affected areas after a driver, vs matched days
# ---------------------------------------------------------------------------
def _daily_counts(problems):
    counts = {}
    for p in problems:
        if p.get("area"):
            key = (p["day"], p["area"], p["category"])
            counts[key] = counts.get(key, 0) + 1
    return counts


def _window_total(counts, areas, category, first_day):
    return sum(counts.get((first_day + timedelta(days=i), a, category), 0)
               for i in range(UPLIFT_DAYS) for a in areas)


def uplift_table(problems, events, categories, until):
    """[{driver, category, uplift, after, normal, n_events, confidence}] for past events only."""
    counts = _daily_counts(problems)
    rows = []
    for kind in TYPES:
        past = [e for e in events if e["type"] == kind and e["coverage"] == "inside"
                and e["areas"] and e["start"] + timedelta(days=UPLIFT_DAYS) <= until]
        if not past:
            continue
        busy = {d for e in past for d in event_days(e)}
        for category in categories:
            after, normal = [], []
            for e in past:
                after.append(_window_total(counts, e["areas"], category, e["start"]))
                # Comparable days: same weekday 2 to 6 weeks either side, clear of any such event.
                for weeks in (-6, -4, -2, 2, 4, 6):
                    d = e["start"] + timedelta(weeks=weeks)
                    if d + timedelta(days=UPLIFT_DAYS) > until:
                        continue
                    if any(d + timedelta(days=i) in busy for i in range(UPLIFT_DAYS)):
                        continue
                    normal.append(_window_total(counts, e["areas"], category, d))
            if not normal:
                continue
            a, n = sum(after) / len(after), sum(normal) / len(normal)
            if a == 0 and n == 0:
                continue
            rows.append({"driver": kind, "category": category, "after": round(a, 2), "normal": round(n, 2),
                         "uplift": round(a - n, 2), "n_events": len(past),
                         "confidence": "low" if len(past) < MIN_EVENTS else "medium"})
    return rows


def season_uplift(weekly, until):
    """Leaf-fall weeks vs the four weeks either side, per category, city-wide. weekly: {(week, cat): n}."""
    rows = []
    cats = sorted({c for _, c in weekly})
    for category in cats:
        leaf, near = [], []
        for (week, cat), n in weekly.items():
            if cat != category or week > until:
                continue
            woy = week.isocalendar()[1]
            if woy in config.LEAF_WEEKS:
                leaf.append(n)
            elif min(config.LEAF_WEEKS) - 4 <= woy < min(config.LEAF_WEEKS) or \
                    max(config.LEAF_WEEKS) < woy <= max(config.LEAF_WEEKS) + 4:
                near.append(n)
        if leaf and near:
            a, n = sum(leaf) / len(leaf), sum(near) / len(near)
            seasons = len({w.year for (w, c) in weekly if c == category and w.isocalendar()[1] in config.LEAF_WEEKS})
            rows.append({"driver": "leaf_fall", "category": category, "after": round(a, 2), "normal": round(n, 2),
                         "uplift": round(a - n, 2), "n_events": seasons,
                         "confidence": "low" if seasons < MIN_EVENTS else "medium"})
    return [r for r in rows if abs(r["uplift"]) >= 0.5]

"""SYNTHETIC two-year complaint history, so the method can be trained and tested.

The live database holds about four weeks of synthetic reports, which is too
short to learn or test anything. This builds problems on real Southampton
street names with known, planted effects (config.PLANTED) driven by REAL cached
weather and the synthetic event calendar. A model that recovers these effects
proves the pipeline works end to end; it says nothing about the real city.
Every problem carries synthetic=1 and lives only in predict.db's run, never in
the bot's database.
"""

import json
from datetime import datetime, time, timedelta, timezone

import numpy as np

from . import config, events as ev
from .data import geo

CATEGORIES = {   # weekly base rate per street, before street variation
    "litter_street_cleaning": 0.30, "fly_tipping": 0.22, "pothole": 0.16, "graffiti_flyposting": 0.10,
    "dog_fouling": 0.10, "missed_bin": 0.12, "illegal_parking": 0.12, "glass_spillage_hazard": 0.05,
}
SEVERITY = {"glass_spillage_hazard": ("high", 0.7), "pothole": ("high", 0.35), "fly_tipping": ("high", 0.2)}
SURGE_STREET = ("Weston Lane", "Weston")          # example 4: a planted surge, last 48 hours
QUIET_STREET = ("Abbotsfield Close", "Aldermoor")  # example 2: one report in 13 weeks


def _streets(rng, n_other=110):
    rows = json.loads(geo.STREETS_FILE.read_text(encoding="utf-8"))["streets"]
    units, seen = [], set()
    wanted_areas = {a for areas in config.VENUE_AREAS.values() for a in areas}
    for name, area, *_ in rows:
        if area in wanted_areas and (name, area) not in seen:
            seen.add((name, area))
            units.append((name, area))
    others = [(n, a) for n, a, *_ in rows if (n, a) not in seen and a]
    for i in rng.choice(len(others), size=min(n_other, len(others)), replace=False):
        units.append(others[i])
    for fixed in (SURGE_STREET, QUIET_STREET):
        if fixed not in units:
            units.append(fixed)
    return units


def generate(weather_days, events, end, weeks=config.SYNTH_WEEKS, seed=config.SYNTH_SEED, now=None):
    rng = np.random.default_rng(seed)
    start = end - timedelta(weeks=weeks)
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    units = _streets(rng)
    cats = list(CATEGORIES)

    # Street base rates: most streets quiet, a few busy (gamma), main roads busier.
    base = np.empty((len(units), len(cats)))
    for u, (name, area) in enumerate(units):
        busy = 2.0 if any(w in name for w in ("High Street", "Road", "Bar")) else 1.0
        for c, cat in enumerate(cats):
            base[u, c] = rng.gamma(0.7, CATEGORIES[cat] / 0.7) * busy / 7.0
    quiet = units.index(QUIET_STREET)
    base[quiet, :] = 0.0

    area_of = np.array([a for _, a in units])
    c_idx = {c: i for i, c in enumerate(cats)}
    lam = np.repeat(base[None, :, :], len(days), axis=0)          # day x unit x category

    for d, day in enumerate(days):
        woy = day.isocalendar()[1]
        if woy in config.LEAF_WEEKS:
            lam[d, :, c_idx["litter_street_cleaning"]] *= 1.8
        if day.weekday() in (5, 6, 0):
            lam[d, :, c_idx["litter_street_cleaning"]] *= 1.2
        rain14, frost14 = _weather(weather_days, day, 14)
        if rain14 is not None:
            lam[d, :, c_idx["pothole"]] *= 1.0 + 0.18 * frost14 + 0.012 * rain14

    for e in events:
        if e["coverage"] != "inside" or not e["areas"]:
            continue
        mask = np.isin(area_of, e["areas"])
        for day in ev.event_days(e):
            d = (day - start).days
            if not 0 <= d < len(days):
                continue
            if e["type"] == "match_day":
                lam[d][np.ix_(mask, [c_idx["litter_street_cleaning"], c_idx["illegal_parking"]])] *= 3.0
            elif e["type"] == "cruise_call":
                lam[d][np.ix_(mask, [c_idx["litter_street_cleaning"]])] *= 1.6
            elif e["type"] == "university_move_out":
                lam[d][np.ix_(mask, [c_idx["fly_tipping"]])] *= 4.0
                lam[d][np.ix_(mask, [c_idx["missed_bin"]])] *= 3.0

    counts = rng.poisson(lam)
    problems = []
    n = 0
    for d, u, c in zip(*np.nonzero(counts)):
        for _ in range(counts[d, u, c]):
            n += 1
            problems.append(_problem(n, days[d], units[u], cats[c], rng))

    now = now or datetime.now(timezone.utc)
    # Example 2: exactly one problem in the last 13 weeks on a quiet street.
    n += 1
    problems.append(_problem(n, end - timedelta(days=40), QUIET_STREET, "litter_street_cleaning", rng))
    # Example 4: a surge on one street in the last 48 hours.
    for hours in (3, 9, 20, 31, 44):
        n += 1
        p = _problem(n, (now - timedelta(hours=hours)).date(), SURGE_STREET, "fly_tipping", rng)
        p["at"] = now - timedelta(hours=hours)
        problems.append(p)
    problems.sort(key=lambda p: p["at"])
    return problems, units


def _problem(n, day, unit, category, rng):
    sev_high = SEVERITY.get(category)
    severity = "high" if sev_high and rng.random() < sev_high[1] else ("medium" if rng.random() < 0.6 else "low")
    at = datetime.combine(day, time(int(rng.integers(6, 23)), int(rng.integers(0, 60))), tzinfo=timezone.utc)
    return {"id": f"S-{n:06d}", "at": at, "day": day, "category": category, "street": unit[0],
            "area": unit[1], "severity": severity, "hazard": category == "glass_spillage_hazard",
            "status": "resolved", "noticed": 1 + int(rng.poisson(0.25)), "synthetic": 1}


def _weather(days, day, length):
    rain = frost = 0.0
    seen = 0
    for i in range(1, length + 1):
        w = days.get(day - timedelta(days=i))
        if w:
            seen += 1
            rain += w["rain"] or 0.0
            frost += 1 if (w["tmin"] is not None and w["tmin"] <= config.FROST_C) else 0
    return (rain, frost) if seen else (None, None)

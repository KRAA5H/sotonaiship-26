"""Surge detection (model 7): a street whose last 24 to 72 hours are unusually high
against its own smoothed weekly rate.

p = P(X >= count) for X ~ Poisson(weekly_rate x hours / 168). An alert needs
p below config.SURGE_P AND at least config.SURGE_MIN_COUNT distinct problems,
and the same street and category is not alerted again within the cooldown.
The simple comparison is a fixed rule: 3 problems in 24 hours.
"""

from bisect import bisect_left, bisect_right
from datetime import timedelta

from scipy.stats import poisson

from . import config

FLOOR_RATE = 0.05   # a street with no history still has some chance of a report


def detect(problems, rates, now, recent_alerts=()):
    """Alerts for every (street, category) with recent problems. rates: {(street, category): weekly}."""
    longest = max(config.SURGE_WINDOWS_H)
    recent = [p for p in problems if p.get("street") and now - timedelta(hours=longest) <= p["at"] <= now]
    groups = {}
    for p in recent:
        groups.setdefault((p["street"], p["category"]), []).append(p)
    cooled = {(a["street"], a["category"]) for a in recent_alerts}
    alerts = []
    for (street, category), items in groups.items():
        if (street, category) in cooled:
            continue
        weekly = max(rates.get((street, category), FLOOR_RATE), FLOOR_RATE)
        best = None
        for hours in config.SURGE_WINDOWS_H:
            count = sum(1 for p in items if p["at"] >= now - timedelta(hours=hours))
            expected = weekly * hours / 168
            p_value = float(poisson.sf(count - 1, expected)) if count else 1.0
            if best is None or p_value < best["p_value"]:
                best = {"window_h": hours, "count": count, "expected": round(expected, 3), "p_value": p_value}
        fixed_hits = sum(1 for p in items if p["at"] >= now - timedelta(hours=config.FIXED_RULE[1]))
        fixed = fixed_hits >= config.FIXED_RULE[0]
        if best["p_value"] < config.SURGE_P and best["count"] >= config.SURGE_MIN_COUNT:
            alerts.append({"street": street, "area": items[0].get("area"), "category": category,
                           "weekly_rate": round(weekly, 3), "fixed_rule": fixed,
                           "synthetic": max(p["synthetic"] for p in items), **best})
    return sorted(alerts, key=lambda a: a["p_value"])


def compare_rules(problems, rates, end, days=84):
    """Backtest over the last `days`: alerts each rule raises (checked once a day),
    and how often the street then had at least one more problem in the next 7 days."""
    start = end - timedelta(days=days + 3)
    by_key = {}
    for p in problems:
        if p.get("street") and p["at"] >= start:
            by_key.setdefault((p["street"], p["category"]), []).append(p["at"])
    result = {"model": {"alerts": 0, "followed": 0}, "fixed": {"alerts": 0, "followed": 0}, "days": days}
    for key, times in by_key.items():
        if len(times) < config.SURGE_MIN_COUNT:
            continue
        times.sort()
        weekly = max(rates.get(key, FLOOR_RATE), FLOOR_RATE)
        count = lambda a, b: bisect_right(times, b) - bisect_left(times, a)  # noqa: E731
        last = {"model": None, "fixed": None}
        for d in range(days, 0, -1):
            check = end - timedelta(days=d)
            n72 = count(check - timedelta(hours=72), check)
            if n72 < config.SURGE_MIN_COUNT:
                continue
            best = min(float(poisson.sf(count(check - timedelta(hours=h), check) - 1, weekly * h / 168))
                       for h in config.SURGE_WINDOWS_H)
            fired = {"model": best < config.SURGE_P,
                     "fixed": count(check - timedelta(hours=config.FIXED_RULE[1]), check) >= config.FIXED_RULE[0]}
            for rule, hit in fired.items():
                if not hit or (last[rule] and check - last[rule] < timedelta(hours=config.SURGE_COOLDOWN_H)):
                    continue
                last[rule] = check
                result[rule]["alerts"] += 1
                if count(check + timedelta(seconds=1), check + timedelta(days=7)):
                    result[rule]["followed"] += 1
    return result

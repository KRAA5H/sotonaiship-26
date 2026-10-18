"""Action planner: every risk becomes a preventive job an officer can approve.

Rules first, no model: preventive_actions.json maps each driver to an action,
a lead time, a suggested team and checklist steps (all ASSUMED, confirm with
the council).

  do_by    = expected problem date - lead time
  score    = expected volume x harm x urgency x confidence   (shown with its parts)
  urgency  rises from 1.0 to 2.0 as do_by approaches; overdue jobs are 2.0
  sort     do_by first, then score; overdue jobs first

Jobs on the same area, same action and same expected date merge into one job
with every reason kept. A low-confidence forecast never becomes a job.
"""

import csv
import io
import json
from datetime import date, timedelta

from . import config

DRIVER_ORDER = ("event", "weather", "season", "history")


def load_config():
    return json.loads(config.ACTIONS_JSON.read_text(encoding="utf-8"))["actions"]


def harm(categories):
    return max((config.HARM.get(c, config.HARM_DEFAULT) for c in categories), default=config.HARM_DEFAULT)


def urgency(do_by, today):
    days = (do_by - today).days
    if days < 0:
        return 2.0
    return round(1.0 + max(0.0, min(1.0, (7 - days) / 7)), 2)


def _expected_date(driver_key, week_start, events):
    """Event jobs aim at the event's first day in the week; others at the week's first day."""
    for e in events:
        if e["type"] == driver_key and week_start <= e["start"] < week_start + timedelta(days=7):
            return e["start"]
    return week_start


def plan(forecasts, surges, events, today, week_start):
    cfg = load_config()
    groups = {}
    for f in forecasts:
        if f["confidence"] == "low" or not f["drivers"]:
            continue
        if f["expected"] < config.RISK_MIN_EXPECTED and f["drivers"][0][0] == "history":
            continue
        kind, key, text = sorted(f["drivers"], key=lambda d: DRIVER_ORDER.index(d[0]))[0]
        rule = cfg.get(key)
        if not rule:
            continue
        expected = _expected_date(key, week_start, events)
        gkey = f"{key}|{f['area'] or f['street']}|{expected}"
        g = groups.setdefault(gkey, {"key": gkey, "driver": kind, "driver_key": key, "rule": rule,
                                     "area": f["area"], "expected": expected, "items": []})
        g["items"].append((f, text))

    plans = []
    for g in groups.values():
        items = g["items"]
        rule = g["rule"]
        do_by = g["expected"] - timedelta(days=rule["lead_days"])
        if do_by < today and g["driver"] != "event":
            # A season or weather spell already under way: due now, not "overdue since".
            do_by = today
        volume = round(sum(f["expected"] for f, _ in items), 2)
        cats = sorted({f["category"] for f, _ in items})
        best = max(items, key=lambda it: it[0]["expected"])[0]
        conf_w = config.CONFIDENCE_WEIGHT[best["confidence"]]
        h, u = harm(cats), urgency(do_by, today)
        reasons = sorted({t for _, t in items} | {_history(f) for f, _ in items if f["r13"]})
        plans.append({
            "key": g["key"], "driver": g["driver"], "driver_key": g["driver_key"], "action": rule["action"],
            "team": rule["team"], "area": g["area"],
            "streets": sorted({f["street"] for f, _ in items}, key=lambda s: -sum(
                f["expected"] for f, _ in items if f["street"] == s))[:8],
            "categories": cats, "expected_date": str(g["expected"]), "do_by": str(do_by),
            "steps": rule["steps"], "reasons": reasons, "confidence": best["confidence"],
            "volume": volume, "volume_low": sum(f["low"] for f, _ in items),
            "volume_high": sum(f["high"] for f, _ in items), "harm": h, "urgency": u, "conf_weight": conf_w,
            "score": round(volume * h * u * conf_w * 10, 1),
            "synthetic": max(f["synthetic"] for f, _ in items),
        })

    surge_rule = cfg["surge"]
    for s in surges:
        h = harm([s["category"]])
        volume = float(s["count"])
        plans.append({
            "key": f"surge|{s['street']}|{s['category']}|{today}", "driver": "surge", "driver_key": "surge",
            "action": surge_rule["action"], "team": surge_rule["team"], "area": s["area"],
            "streets": [s["street"]], "categories": [s["category"]], "expected_date": str(today),
            "do_by": str(today), "steps": surge_rule["steps"],
            "reasons": [f"{s['count']} problems in {s['window_h']} hours vs a normal {s['weekly_rate']} a week "
                        f"(p {_p(s['p_value'])})"],
            "confidence": "high", "volume": volume, "volume_low": s["count"], "volume_high": s["count"],
            "harm": h, "urgency": 2.0, "conf_weight": 0.9, "score": round(volume * h * 2.0 * 0.9 * 10, 1),
            "synthetic": s["synthetic"],
        })
    return sort_plans(plans, today)


def sort_plans(plans, today):
    def key(p):
        do_by = date.fromisoformat(p["do_by"])
        return (do_by >= today, do_by, -p["score"])
    return sorted(plans, key=key)


def _history(f):
    return f"{f['r13']} problems on {f['street']} in the last 13 weeks"


def _p(value):
    return "< 0.001" if value < 0.001 else f"{value:.3f}"


def work_order_csv(rows):
    """Approved and scheduled plans as a CSV work order, sorted by do_by."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["do_by", "action", "streets", "area", "team (confirm)", "expected_date", "status",
                     "reasons", "steps", "synthetic"])
    for r in sorted(rows, key=lambda r: r["do_by"]):
        writer.writerow([r["do_by"], r["action"], "; ".join(json.loads(r["streets"])), r["area"] or "",
                         r["team"], r["expected_date"], r["status"], " | ".join(json.loads(r["reasons"])),
                         " | ".join(json.loads(r["steps"])), "yes" if r["synthetic"] else "no"])
    return out.getvalue()

"""The Forecast section of the council dashboard: /council/forecast.

A Blueprint nested on website.site, so it appears wherever the dashboard is
served, behind the same login, using the same base template and stylesheet.
It reads only predict.db: a page load never retrains or calls a model.
"""

import json
from datetime import date, datetime, timedelta, timezone

from flask import Blueprint, Response, jsonify, render_template, request, url_for

from . import actions, config, store

forecast = Blueprint("forecast", __name__, url_prefix="/council/forecast",
                     template_folder="templates", static_folder="static", static_url_path="/assets")

LABELS = {
    "litter_street_cleaning": "Litter and street cleaning", "fly_tipping": "Fly-tipping", "pothole": "Potholes",
    "graffiti_flyposting": "Graffiti", "dog_fouling": "Dog fouling", "missed_bin": "Missed bins",
    "illegal_parking": "Parking", "glass_spillage_hazard": "Glass and spillages", "dead_animal": "Dead animals",
}
DRIVER_LABELS = {"event": "Event", "weather": "Weather", "season": "Season", "history": "History", "surge": "Surge"}


def _denied():
    import website  # the dashboard's own login check, imported late to avoid a cycle
    return website._council_denied()


def _age_hours(stamp):
    try:
        then = datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return None
    return (datetime.now(timezone.utc) - then).total_seconds() / 3600


@forecast.app_template_filter("label")
def _label(category):
    return LABELS.get(category, (category or "").replace("_", " ").capitalize())


@forecast.app_template_filter("dmy")
def _dmy(value):
    try:
        d = date.fromisoformat(str(value)[:10])
    except ValueError:
        return value
    return f"{d:%a} {d.day} {d:%b}"


@forecast.get("")
def page():
    denied = _denied()
    if denied:
        return denied
    conn = store.connect()
    try:
        return render_template("forecast.html", **_context(conn, request.args.get("category") or ""))
    finally:
        conn.close()


def _context(conn, category):
    run = store.latest_run(conn, "batch")
    last_any = store.latest_run(conn, "batch", ok_only=False)
    surge_run = store.latest_run(conn, "surge")
    today = datetime.now(timezone.utc).date()
    ctx = {"run": run, "today": today, "category": category, "labels": LABELS, "driver_labels": DRIVER_LABELS,
           "warning": None, "sources": [], "metrics": {}}
    if last_any and last_any["status"] == "failed":
        ctx["warning"] = f"The latest forecast run failed ({last_any['error']}). Showing the last good run."
    if run is None:
        ctx["warning"] = "No forecast has been run yet. Run: python -m predict.run"
        return ctx
    age = _age_hours(run["finished_at"])
    if age is not None and age > config.STALE_HOURS:
        ctx["warning"] = f"This forecast is {age:.0f} hours old. Treat it as out of date until the next run."
    ctx["age_hours"] = age
    ctx["sources"] = json.loads(run["sources"] or "[]")
    ctx["metrics"] = json.loads(run["metrics"] or "{}")
    ctx["surge_run"] = surge_run

    rows = [dict(r) for r in conn.execute("SELECT * FROM pred_forecasts WHERE run_id = ?", (run["id"],))]
    for r in rows:
        r["drivers"] = json.loads(r["drivers"] or "[]")
    risks = [r for r in rows if r["confidence"] != "low" and r["expected"] >= config.RISK_MIN_EXPECTED
             and any(d[0] != "history" for d in r["drivers"])]
    ctx["risks"] = sorted(risks, key=lambda r: -r["expected"])[:9]
    ctx["risk_count"] = len(risks)

    plans = [dict(r) for r in conn.execute("SELECT * FROM pred_actions")]
    for p in plans:
        for k in ("streets", "categories", "steps", "reasons"):
            p[k] = json.loads(p[k] or "[]")
        p["overdue"] = p["status"] in ("proposed", "approved", "scheduled") and date.fromisoformat(p["do_by"]) < today
    open_plans = [p for p in plans if p["status"] in ("proposed", "approved", "scheduled")]
    ctx["priority"] = sorted(open_plans, key=lambda p: (not p["overdue"], p["do_by"], -p["score"]))
    ctx["board"] = {s: [p for p in sorted(plans, key=lambda p: (p["do_by"], -p["score"])) if p["status"] == s]
                    for s in store.STATUSES}

    since = (datetime.now(timezone.utc) - timedelta(hours=72)).isoformat(timespec="seconds")
    ctx["surges"] = [dict(r) for r in conn.execute(
        "SELECT * FROM pred_surges WHERE detected_at >= ? ORDER BY p_value", (since,))]
    seen, unique = set(), []
    for s in ctx["surges"]:
        if (s["street"], s["category"]) not in seen:
            seen.add((s["street"], s["category"]))
            unique.append(s)
    ctx["surges"] = unique

    ctx["heat"] = _heat(rows, category)
    ctx["categories"] = sorted({r["category"] for r in rows})
    low = [r for r in rows if r["confidence"] == "low" and r["r13"] >= 1]
    ctx["failure"] = next((r for r in low if r["street"] == "Abbotsfield Close"), low[0] if low else None)
    ctx["low_count"] = sum(1 for r in rows if r["confidence"] == "low")
    ctx["events"] = [dict(r) for r in conn.execute(
        "SELECT * FROM pred_events WHERE run_id = ? ORDER BY start_date", (run["id"],))]
    ctx["uplift"] = [dict(r) for r in conn.execute(
        "SELECT * FROM pred_uplift WHERE run_id = ? ORDER BY uplift DESC LIMIT 10", (run["id"],))]
    ctx["outcomes"] = _prevention(conn, plans)
    return ctx


def _heat(rows, category):
    """Area x category expected problems next week. Areas, not streets: no league table of homes."""
    cells, totals = {}, {}
    for r in rows:
        if category and r["category"] != category:
            continue
        area = r["area"] or "Area not known"
        cells[(area, r["category"])] = cells.get((area, r["category"]), 0) + r["expected"]
        totals[area] = totals.get(area, 0) + r["expected"]
    areas = sorted(totals, key=lambda a: -totals[a])[:18]
    cats = sorted({c for _, c in cells})
    peak = max(cells.values(), default=1) or 1
    grid = [{"area": a, "cells": [{"cat": c, "value": cells.get((a, c), 0.0),
                                   "level": min(5, int(5 * cells.get((a, c), 0.0) / peak + 0.999))} for c in cats]}
            for a in sorted(areas)]
    return {"cats": cats, "rows": grid}


def _prevention(conn, plans):
    """After a done job vs after none: an association, never a cause."""
    done = [p for p in plans if p["status"] == "done"]
    ended = conn.execute("SELECT COUNT(*) FROM pred_outcomes WHERE source = 'forecast'").fetchone()[0]
    return {"done": len(done), "ended_weeks": ended,
            "raised": len(plans), "approved": sum(1 for p in plans if p["status"] in ("approved", "scheduled", "done"))}


@forecast.post("/plans/<path:key>/status")
def set_plan_status(key):
    denied = _denied()
    if denied:
        return denied
    # Same CSRF guard as the dashboard: a cross-site form cannot send JSON with this header.
    if not request.is_json or request.headers.get("X-Requested-With") != "kerbside":
        return jsonify({"ok": False, "error": "send JSON from the forecast page"}), 400
    body = request.get_json(silent=True) or {}
    conn = store.connect()
    try:
        ok, message = store.set_action_status(conn, key, body.get("status"), body.get("note"))
    finally:
        conn.close()
    return (jsonify({"ok": True, "status": message}) if ok
            else (jsonify({"ok": False, "error": message}), 400))


@forecast.get("/work-order.csv")
def work_order():
    denied = _denied()
    if denied:
        return denied
    conn = store.connect()
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM pred_actions WHERE status IN ('approved', 'scheduled') ORDER BY do_by")]
    finally:
        conn.close()
    return Response(actions.work_order_csv(rows), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=preventive-work-order.csv"})


def council_link(street):
    return url_for("website.council") + "?q=" + (street or "")

"""Nightly batch: rebuild the forecast from all history and save it to predict.db.

Run from code/:   python -m predict.run

1. Live complaints, read-only from kerbside.db (a failure keeps the last run)
2. Weather from Open-Meteo, cached (missing weather is said, not hidden)
3. Events: the synthetic calendar plus data/events.csv
4. The SYNTHETIC two-year history (labelled everywhere)
5. Panel, time-based backtest against the baseline, final model, next week's forecast
6. Event and season uplift, surge alerts, the action plan
7. Outcomes: actual counts for any earlier forecast week that has now ended
"""

import json
import sys
import traceback
from datetime import datetime, timedelta, timezone

from . import actions, config, data, events as ev, models, store, surge, synth, weather


def main(now=None):
    now = now or datetime.now(timezone.utc)
    today = now.date()
    conn = store.connect()
    run_id = store.start_run(conn, "batch")
    sources = []
    try:
        live_rows = data.load_live()
        live = data.distinct_problems(live_rows)
        sources.append({"name": "Kerbside live reports (read-only)", "rows": len(live_rows),
                        "synthetic_rows": sum(r["synthetic"] for r in live_rows), "as_of": now.isoformat(timespec="seconds")})

        hist_start = today - timedelta(weeks=config.SYNTH_WEEKS + 4)
        cache = weather.refresh(hist_start, today - timedelta(days=1))
        days = weather.daily(cache)
        sources.append({"name": weather.SOURCE if cache else "Weather unavailable: forecast runs without it",
                        "fetched": (cache or {}).get("history_fetched_at"),
                        "forecast_fetched": (cache or {}).get("forecast_fetched_at"),
                        "error": (cache or {}).get("last_error")})

        events = ev.synthetic_events(hist_start, today + timedelta(days=21)) + ev.load_csv()
        sources.append({"name": "Event calendar: synthetic demo calendar plus data/events.csv",
                        "rows": len(events)})

        history, units = synth.generate(days, events, today, now=now)
        sources.append({"name": "SYNTHETIC two-year complaint history (planted effects, see PREDICTION.md)",
                        "rows": len(history), "streets": len(units)})
        problems = history + live

        this_week = data.week_start(today)
        forecast_week = this_week + timedelta(days=7)
        panel = models.build_panel(problems, days, events, this_week)
        bt = models.backtest(panel)
        model = models.fit(panel.dropna(subset=["target"]))
        forecasts = models.forecast(panel, model, forecast_week)

        synthetic = int(any(p["synthetic"] for p in problems))
        rates = {(f["street"], f["category"]): f["rate"] for f in forecasts}
        cooled = conn.execute("SELECT street, category FROM pred_surges WHERE detected_at >= ?",
                              ((now - timedelta(hours=config.SURGE_COOLDOWN_H)).isoformat(timespec="seconds"),)
                              ).fetchall()
        alerts = surge.detect(problems, rates, now, [dict(r) for r in cooled])
        surge_bt = surge.compare_rules(problems, rates, now)

        weekly = {}
        for p in problems:
            k = (data.week_start(p["day"]), p["category"])
            weekly[k] = weekly.get(k, 0) + 1
        uplift = ev.uplift_table(problems, events, sorted(synth.CATEGORIES), today) + \
            ev.season_uplift(weekly, this_week)

        upcoming = [e for e in events if today <= e["start"] <= today + timedelta(days=14)]
        plans = actions.plan(forecasts, alerts, upcoming, today, forecast_week)

        store.save_forecasts(conn, run_id, forecasts)
        store.save_surges(conn, run_id, alerts)
        store.save_actions(conn, run_id, plans)
        store.save_uplift(conn, run_id, uplift, synthetic)
        shown = {e["id"]: e for e in upcoming + [e for e in events if e["coverage"] == "outside"]}
        store.save_events(conn, run_id, list(shown.values()))
        _record_outcomes(conn, run_id, panel, bt, synthetic)

        metrics = {"backtest": {k: v for k, v in (bt or {}).items() if k != "detail"},
                   "surge_backtest": surge_bt, "planted": config.PLANTED,
                   "counts": {"forecasts": len(forecasts), "risks": sum(1 for f in forecasts if f["drivers"]),
                              "low_confidence": sum(1 for f in forecasts if f["confidence"] == "low"),
                              "surges": len(alerts), "plans": len(plans)}}
        store.finish_run(conn, run_id, "ok", synthetic, str(forecast_week), sources, metrics)
        print(json.dumps({"run": run_id, "forecast_week": str(forecast_week), **metrics["counts"],
                          "capture": (bt or {}).get("capture"), "lead": (bt or {}).get("lead")}, default=str))
        return run_id
    except Exception as error:  # noqa: BLE001 - a failed run must be visible on the page, not hidden
        store.finish_run(conn, run_id, "failed", sources=sources, error=f"{type(error).__name__}: {error}"[:500])
        traceback.print_exc()
        return None
    finally:
        conn.close()


def _record_outcomes(conn, run_id, panel, bt, synthetic):
    """Backtest weeks, and any earlier forecast week that has now ended."""
    detail = (bt or {}).get("detail")
    if detail is not None and not conn.execute(
            "SELECT 1 FROM pred_outcomes WHERE source = 'backtest' LIMIT 1").fetchone():
        store.save_outcomes(conn, run_id, [
            {"week": r.target_week, "street": r.street, "category": r.category, "predicted": round(float(r.pred), 3),
             "baseline": round(float(r.base), 3), "actual": int(r.target), "synthetic": synthetic}
            for r in detail.itertuples(index=False) if r.target or r.pred >= 0.5], "backtest")
    ended = conn.execute(
        "SELECT DISTINCT week FROM pred_forecasts WHERE week < ? AND week NOT IN "
        "(SELECT week FROM pred_outcomes WHERE source = 'forecast')", (str(data.week_start(data.today())),)
    ).fetchall()
    for (week,) in ended:
        actual = panel[panel["week"] == data.as_date(week)].set_index(["street", "category"])["y"]
        rows = conn.execute("SELECT street, category, expected, baseline, synthetic FROM pred_forecasts "
                            "WHERE week = ? AND run_id = (SELECT MAX(run_id) FROM pred_forecasts WHERE week = ?)",
                            (week, week)).fetchall()
        store.save_outcomes(conn, run_id, [
            {"week": week, "street": r["street"], "category": r["category"], "predicted": r["expected"],
             "baseline": r["baseline"], "actual": int(actual.get((r["street"], r["category"]), 0)),
             "synthetic": r["synthetic"]} for r in rows], "forecast")


if __name__ == "__main__":
    sys.exit(0 if main() else 1)

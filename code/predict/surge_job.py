"""Light surge check on live reports, every few minutes.

Run from code/:   python -m predict.surge_job          (one check)
                  python -m predict.surge_job --loop   (every 5 minutes)

Reads only reports from the last 72 hours, read-only, and compares them with the
weekly rates the last nightly run saved. It never retrains. If the live
database is locked or missing it does nothing and says so.
"""

import sys
import time
from datetime import datetime, timedelta, timezone

from . import config, data, store, surge

EVERY_S = 300


def check(now=None):
    now = now or datetime.now(timezone.utc)
    conn = store.connect()
    run_id = store.start_run(conn, "surge")
    try:
        since = (now - timedelta(hours=max(config.SURGE_WINDOWS_H))).isoformat(timespec="seconds")
        problems = data.distinct_problems(data.load_live(since=since))
        last = store.latest_run(conn, "batch")
        rates = {}
        if last:
            rates = {(r["street"], r["category"]): r["rate"] for r in conn.execute(
                "SELECT street, category, rate FROM pred_forecasts WHERE run_id = ?", (last["id"],))}
        cooled = conn.execute("SELECT street, category FROM pred_surges WHERE detected_at >= ?",
                              ((now - timedelta(hours=config.SURGE_COOLDOWN_H)).isoformat(timespec="seconds"),)
                              ).fetchall()
        alerts = surge.detect(problems, rates, now, [dict(r) for r in cooled])
        store.save_surges(conn, run_id, alerts)
        store.finish_run(conn, run_id, "ok", int(any(p["synthetic"] for p in problems)),
                         metrics={"checked": len(problems), "alerts": len(alerts)},
                         sources=[{"name": "Kerbside live reports (read-only)", "since": since}])
        return alerts
    except data.Unavailable as error:
        store.finish_run(conn, run_id, "failed", error=f"live database unavailable: {error}")
        return []
    finally:
        conn.close()


if __name__ == "__main__":
    if "--loop" in sys.argv:
        while True:
            print(f"[surge] {len(check())} alerts")
            time.sleep(EVERY_S)
    else:
        print(f"[surge] {len(check())} alerts")

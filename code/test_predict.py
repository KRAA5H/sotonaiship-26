"""Tests for the predictive prevention layer (code/predict/). No network.

Run:
  python code/test_predict.py
"""

import base64
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from predict import actions, config, data, events, models, store, surge  # noqa: E402

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)
TODAY = NOW.date()


def problem(i, day, street="Weston Lane", area="Weston", category="pothole", hours=None, synthetic=1):
    at = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=10)
    if hours is not None:
        at = NOW - timedelta(hours=hours)
    return {"id": f"T-{i}", "at": at, "day": at.date(), "category": category, "street": street, "area": area,
            "severity": "medium", "hazard": False, "status": "new", "noticed": 1, "synthetic": synthetic}


class Distinct(unittest.TestCase):
    def test_duplicates_counted_once_and_kept_as_noticed(self):
        rows = [
            {"id": "R-1", "created_at": "2026-10-01T10:00:00+00:00", "category_id": "pothole",
             "location": "12 Weston Lane", "area": None, "duplicate_of": None, "status": "new"},
            {"id": "R-2", "created_at": "2026-10-01T11:00:00+00:00", "category_id": "pothole",
             "location": "weston ln", "area": None, "duplicate_of": "R-1", "status": "new"},
            {"id": "R-3", "created_at": "2026-10-02T11:00:00+00:00", "category_id": "pothole",
             "location": "Not given", "area": None, "duplicate_of": None, "status": "new"},
        ]
        problems = data.distinct_problems(rows)
        self.assertEqual(len(problems), 2)
        self.assertEqual(problems[0]["noticed"], 2)
        self.assertEqual(problems[0]["street"], "Weston Lane")
        self.assertIsNone(problems[1]["street"], "a missing location never becomes a street")

    def test_street_key(self):
        self.assertEqual(data.street_key("outside 12 weston ln")[0], "Weston Lane")
        self.assertEqual(data.street_key("117 Old Northam Road")[0], "Old Northam Road",
                         "a longer written street must not collapse into a shorter one")
        self.assertEqual(data.street_key("Not given"), (None, None))


class ReadOnly(unittest.TestCase):
    def test_live_database_is_never_written(self):
        tmp = Path(tempfile.mkdtemp())
        db = tmp / "kerbside.db"
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE reports (id TEXT, created_at TEXT, category_id TEXT, status TEXT, "
                     "severity TEXT, location TEXT, duplicate_of TEXT, description TEXT, reporter_ref TEXT)")
        conn.execute("INSERT INTO reports VALUES ('R-1', '2026-10-01T10:00:00+00:00', 'pothole', 'new', "
                     "'high', 'Hill Lane', NULL, 'secret words', 'h-abc')")
        conn.commit()
        conn.close()
        ro = data.connect_ro(db)
        with self.assertRaises(sqlite3.OperationalError):
            ro.execute("DELETE FROM reports")
        ro.close()
        rows = data.load_live(db)
        self.assertEqual(len(rows), 1)
        self.assertNotIn("description", rows[0], "complaint text is never read")
        self.assertNotIn("reporter_ref", rows[0])
        with self.assertRaises(data.Unavailable):
            data.connect_ro(tmp / "missing.db")
        shutil.rmtree(tmp, ignore_errors=True)


def tiny_panel(weeks=30):
    start = data.week_start(TODAY) - timedelta(weeks=weeks)
    probs, i = [], 0
    for w in range(weeks):
        day = start + timedelta(weeks=w, days=2)
        for _ in range(3 if w % 2 else 1):
            i += 1
            probs.append(problem(i, day, "Hill Lane", "Hill", "litter_street_cleaning"))
        if w % 5 == 0:
            i += 1
            probs.append(problem(i, day, "Weston Lane", "Weston", "pothole"))
    i += 1
    probs.append(problem(i, start + timedelta(weeks=weeks - 3), "Quiet Close", "Hill", "pothole"))
    return models.build_panel(probs, {}, [], data.week_start(TODAY))


class Model(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.panel = tiny_panel()

    def test_no_feature_uses_the_target_week(self):
        p = self.panel[(self.panel.street == "Hill Lane")].sort_values("week").reset_index(drop=True)
        for i in range(4, len(p) - 1):
            self.assertAlmostEqual(p.loc[i, "r4"], p.loc[i - 3:i, "y"].mean())
            self.assertEqual(p.loc[i, "target"], p.loc[i + 1, "y"], "target is the NEXT week")
            self.assertEqual(p.loc[i, "target_week"], p.loc[i, "week"] + timedelta(days=7))

    def test_shrinkage_pulls_sparse_streets_toward_the_mean(self):
        last = self.panel[self.panel.week == self.panel.week.max()]
        quiet = last[last.street == "Quiet Close"].iloc[0]
        raw = quiet.r13 / config.HISTORY_WEEKS
        self.assertGreater(quiet.shrunk, raw * 0.5)
        self.assertLess(quiet.shrunk, raw * 2 + 1)

    def test_confidence_and_interval(self):
        self.assertEqual(models.confidence(1), "low")
        self.assertEqual(models.confidence(5), "medium")
        self.assertEqual(models.confidence(12), "high")
        low, high = models.interval(4.0)
        self.assertLessEqual(low, 4)
        self.assertGreaterEqual(high, 4)

    def test_backtest_is_time_based_and_reports_the_baseline(self):
        bt = models.backtest(self.panel, test_weeks=4)
        self.assertEqual(bt["weeks"], 4)
        for key in ("model", "baseline", "random", "best"):
            self.assertIn(key, bt["capture"])
        self.assertLessEqual(bt["capture"]["model"], bt["capture"]["best"] + 1e-9)
        self.assertLessEqual(bt["lead"]["low"], bt["lead"]["mean"])
        self.assertLessEqual(bt["lead"]["mean"], bt["lead"]["high"])


class Surge(unittest.TestCase):
    def test_burst_on_a_quiet_street_alerts_once(self):
        probs = [problem(i, TODAY, hours=h, category="fly_tipping") for i, h in enumerate((3, 9, 20, 31, 44))]
        alerts = surge.detect(probs, {("Weston Lane", "fly_tipping"): 0.5}, NOW)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["count"], 5)
        self.assertLess(alerts[0]["p_value"], 0.001)
        again = surge.detect(probs, {("Weston Lane", "fly_tipping"): 0.5}, NOW, recent_alerts=alerts)
        self.assertEqual(again, [], "cooldown stops a second alert")

    def test_busy_street_is_not_a_surge(self):
        probs = [problem(i, TODAY, hours=h, street="Hill Lane") for i, h in enumerate((5, 30, 60))]
        self.assertEqual(surge.detect(probs, {("Hill Lane", "pothole"): 10.0}, NOW), [])

    def test_two_reports_never_alert(self):
        probs = [problem(i, TODAY, hours=h) for i, h in enumerate((2, 4))]
        self.assertEqual(surge.detect(probs, {}, NOW), [])


class Events(unittest.TestCase):
    def test_utilita_bowl_is_outside_and_makes_no_job(self):
        bowl = [e for e in events.load_csv() if "Utilita" in e["venue"]]
        self.assertTrue(bowl)
        self.assertEqual(bowl[0]["coverage"], "outside")
        self.assertEqual(bowl[0]["outside_council"], "Eastleigh Borough Council")
        self.assertEqual(bowl[0]["areas"], ())

    def test_unconfirmed_event_counts_less(self):
        self.assertEqual(events.weight({"status": "confirmed"}), 1.0)
        self.assertLess(events.weight({"status": "proposed"}), 1.0)

    def test_uplift_shows_how_many_events_it_rests_on(self):
        ev = [e for e in events.synthetic_events(TODAY - timedelta(weeks=20), TODAY) if e["type"] == "match_day"]
        probs = []
        for i, e in enumerate(ev):
            for j in range(4):
                probs.append(problem(i * 10 + j, e["start"], "Britannia Road", "Northam", "litter_street_cleaning"))
        rows = events.uplift_table(probs, ev, ["litter_street_cleaning"], TODAY)
        self.assertTrue(rows)
        self.assertEqual(rows[0]["n_events"], len([e for e in ev if e["start"] + timedelta(days=4) <= TODAY]))
        self.assertGreater(rows[0]["uplift"], 0)


def forecast_row(street, expected, confidence="medium", drivers=None, area="Weston", category="litter_street_cleaning"):
    return {"street": street, "area": area, "category": category, "week": str(TODAY), "expected": expected,
            "low": 0, "high": int(expected * 2) + 1, "baseline": 1.0, "r13": 6, "rate": 0.5,
            "confidence": confidence, "synthetic": 1,
            "drivers": drivers if drivers is not None else [["season", "leaf_fall", "Leaf-fall season"]]}


class Actions(unittest.TestCase):
    def test_merge_deadline_and_score_parts(self):
        week = data.week_start(TODAY) + timedelta(days=7)
        plans = actions.plan([forecast_row("Weston Lane", 3.0), forecast_row("Hill Lane", 2.0),
                              forecast_row("Quiet Close", 5.0, confidence="low")], [], [], TODAY, week)
        self.assertEqual(len(plans), 1, "same area, action and date merge; low confidence makes no job")
        p = plans[0]
        self.assertEqual(sorted(p["streets"]), ["Hill Lane", "Weston Lane"])
        # Lead time 2 days; a season already under way is due today, never "overdue since".
        self.assertEqual(p["do_by"], str(max(week - timedelta(days=2), TODAY)))
        self.assertAlmostEqual(p["score"], round(p["volume"] * p["harm"] * p["urgency"] * p["conf_weight"] * 10, 1))

    def test_event_jobs_target_the_event_day_and_overdue_sorts_first(self):
        week = data.week_start(TODAY) + timedelta(days=7)
        match = {"type": "match_day", "start": week + timedelta(days=5)}
        f = forecast_row("Britannia Road", 4.0, area="Northam",
                         drivers=[["event", "match_day", "Match day nearby"]])
        plans = actions.plan([f], [], [match], TODAY, week)
        self.assertEqual(plans[0]["expected_date"], str(match["start"]))
        self.assertEqual(plans[0]["do_by"], str(match["start"] - timedelta(days=1)))
        old = dict(plans[0], do_by=str(TODAY - timedelta(days=2)), score=1.0)
        self.assertEqual(actions.sort_plans([plans[0], old], TODAY)[0], old)

    def test_surge_becomes_a_same_day_job(self):
        s = {"street": "Weston Lane", "area": "Weston", "category": "fly_tipping", "count": 5, "window_h": 48,
             "weekly_rate": 0.5, "p_value": 1e-6, "synthetic": 1}
        plans = actions.plan([], [s], [], TODAY, TODAY)
        self.assertEqual(plans[0]["do_by"], str(TODAY))
        self.assertIn("5 problems in 48 hours", plans[0]["reasons"][0])


class Store(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.conn = store.connect(self.tmp / "p.db")
        self.run = store.start_run(self.conn, "batch")
        week = data.week_start(TODAY) + timedelta(days=7)
        store.save_actions(self.conn, self.run, actions.plan([forecast_row("Weston Lane", 3.0)], [], [], TODAY, week))
        self.conn.commit()
        self.key = self.conn.execute("SELECT key FROM pred_actions").fetchone()[0]

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_status_flow_is_audited(self):
        self.assertEqual(store.set_action_status(self.conn, self.key, "done")[0], False, "must be approved first")
        self.assertTrue(store.set_action_status(self.conn, self.key, "approved")[0])
        self.assertTrue(store.set_action_status(self.conn, self.key, "done")[0])
        audit = self.conn.execute("SELECT from_status, to_status FROM pred_action_audit ORDER BY id").fetchall()
        self.assertEqual([tuple(a) for a in audit], [("proposed", "approved"), ("approved", "done")])

    def test_dismiss_needs_a_reason(self):
        self.assertFalse(store.set_action_status(self.conn, self.key, "dismissed", "")[0])
        self.assertTrue(store.set_action_status(self.conn, self.key, "dismissed", "already cleared")[0])

    def test_rerun_keeps_the_officers_decision(self):
        store.set_action_status(self.conn, self.key, "approved")
        week = data.week_start(TODAY) + timedelta(days=7)
        store.save_actions(self.conn, self.run, actions.plan([forecast_row("Weston Lane", 9.0)], [], [], TODAY, week))
        row = self.conn.execute("SELECT status, volume FROM pred_actions WHERE key = ?", (self.key,)).fetchone()
        self.assertEqual(row[0], "approved")
        self.assertEqual(row[1], 9.0)

    def test_work_order_csv(self):
        store.set_action_status(self.conn, self.key, "approved")
        rows = [dict(r) for r in self.conn.execute("SELECT * FROM pred_actions WHERE status = 'approved'")]
        csv_text = actions.work_order_csv(rows)
        self.assertIn("Sweep leaves and clear drains", csv_text)
        self.assertIn(",yes", csv_text, "synthetic is marked on the work order")


class Page(unittest.TestCase):
    """The Forecast section inside the existing dashboard, read from a small predict.db."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.old = config.PREDICT_DB
        config.PREDICT_DB = self.tmp / "predict.db"
        conn = store.connect()
        run = store.start_run(conn, "batch")
        rows = [forecast_row("Weston Lane", 3.0), forecast_row("Abbotsfield Close", 0.1, confidence="low", drivers=[])]
        rows[1]["r13"] = 1
        store.save_forecasts(conn, run, rows)
        week = data.week_start(TODAY) + timedelta(days=7)
        store.save_actions(conn, run, actions.plan(rows, [], [], TODAY, week))
        store.save_events(conn, run, [e for e in events.load_csv() if e["coverage"] == "outside"])
        store.finish_run(conn, run, "ok", 1, str(week), [{"name": "test"}],
                         {"backtest": {"top_n": 10, "weeks": 4, "test_from": "2026-09-01", "test_to": "2026-09-22",
                                       "capture": {"model": 0.1, "baseline": 0.08, "random": 0.02, "best": 0.2},
                                       "mae": {"model": 0.3, "baseline": 0.31},
                                       "deviance": {"model": 0.5, "baseline": 1.0},
                                       "lead": {"mean": 0.02, "low": 0.01, "high": 0.03}}})
        conn.close()
        import website
        self.client = website.create_app(council_password="pw").test_client()
        self.auth = {"Authorization": "Basic " + base64.b64encode(b"x:pw").decode()}

    def tearDown(self):
        config.PREDICT_DB = self.old
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_login_banner_failure_cases_and_no_em_dash(self):
        self.assertEqual(self.client.get("/council/forecast").status_code, 401)
        page = self.client.get("/council/forecast", headers=self.auth).get_data(as_text=True)
        self.assertIn("SYNTHETIC DEMO DATA", page)
        self.assertIn("Abbotsfield Close", page)
        self.assertIn("low confidence", page)
        self.assertIn("Outside Southampton City Council", page)
        self.assertIn("Eastleigh Borough Council", page)
        self.assertIn("Sweep leaves and clear drains", page)
        self.assertNotIn("—", page)

    def test_stale_run_warns(self):
        conn = store.connect()
        conn.execute("UPDATE pred_runs SET finished_at = ?",
                     ((datetime.now(timezone.utc) - timedelta(hours=30)).isoformat(timespec="seconds"),))
        conn.commit()
        conn.close()
        page = self.client.get("/council/forecast", headers=self.auth).get_data(as_text=True)
        self.assertIn("out of date", page)

    def test_failed_run_warns_and_keeps_the_last_good_one(self):
        conn = store.connect()
        run = store.start_run(conn, "batch")
        store.finish_run(conn, run, "failed", error="Unavailable: database is locked")
        conn.close()
        page = self.client.get("/council/forecast", headers=self.auth).get_data(as_text=True)
        self.assertIn("latest forecast run failed", page)
        self.assertIn("Weston Lane", page)

    def test_status_change_needs_the_json_header(self):
        conn = store.connect()
        key = conn.execute("SELECT key FROM pred_actions").fetchone()[0]
        conn.close()
        from urllib.parse import quote
        url = "/council/forecast/plans/" + quote(key, safe="") + "/status"
        self.assertEqual(self.client.post(url, json={"status": "approved"}, headers=self.auth).status_code, 400)
        r = self.client.post(url, json={"status": "approved"}, headers={**self.auth, "X-Requested-With": "kerbside"})
        self.assertEqual(r.get_json()["status"], "approved")


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""Tests for code/priority.py and the priority shown on /council.

Run:
  python code/test_priority.py
"""

import base64
import sys
import tempfile
import unittest
import unittest.mock
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import priority
import tools
import website

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)
GROUPS = {"pothole": "roads_and_parking", "fly_tipping": "street_cleansing", "noise_nuisance": "neighbourhood_nuisance",
          "missed_bin": "bins"}


def report(rid="R-1", category="pothole", location="12 Portswood Road", severity="high", status="new", days=0):
    return {"id": rid, "category_id": category, "location": location, "severity": severity, "status": status,
            "created_at": (NOW - timedelta(days=days)).isoformat()}


def score(r, others=None, groups=GROUPS):
    return priority.priority(r, others if others is not None else [r], groups, NOW)


class FactorTest(unittest.TestCase):
    def test_returns_score_and_four_factors(self):
        result = score(report())
        self.assertEqual(set(result["factors"]), {"severity", "exposure", "cluster", "age_days"})
        self.assertIsInstance(result["score"], int)
        self.assertTrue(result["explanation"].endswith("."))

    def test_severity(self):
        self.assertGreater(score(report(severity="high"))["score"], score(report(severity="medium"))["score"])
        self.assertGreater(score(report(severity="medium"))["score"], score(report(severity="low"))["score"])

    def test_missing_severity_counts_as_medium_and_says_so(self):
        unset = score(report(severity=None))
        self.assertEqual(unset["score"], score(report(severity="medium"))["score"])
        self.assertIn("Not set", unset["factors"]["severity"]["label"])
        self.assertIn("Not set", unset["explanation"])

    def test_exposure_comes_from_the_category_group(self):
        road = score(report(category="pothole"))
        nuisance = score(report(category="noise_nuisance"))
        self.assertGreater(road["factors"]["exposure"]["value"], nuisance["factors"]["exposure"]["value"])
        self.assertGreater(road["score"], nuisance["score"])

    def test_unknown_group_gets_the_default_exposure(self):
        result = score(report(category="something_new"))
        self.assertEqual(result["factors"]["exposure"]["value"], priority.EXPOSURE_DEFAULT[0])


class ClusterTest(unittest.TestCase):
    def test_counts_open_reports_of_the_same_category_at_the_same_place(self):
        target = report("R-1", location="12 Portswood Road")
        others = [target,
                  report("R-2", location="12 portswood road."),             # same place, other spelling
                  report("R-3", location="12  Portswood   Road"),           # extra spaces
                  report("R-4", category="fly_tipping"),                    # other category
                  report("R-5", status="resolved"),                         # resolved
                  report("R-6", location="12 Portswood Road North")]        # a different road
        result = score(target, others)
        self.assertEqual(result["factors"]["cluster"]["value"], 3)
        self.assertIn("3 open reports at this place", result["explanation"])

    def test_same_normalisation_as_the_duplicate_rule(self):
        a, b = "Weston Lane", "weston lane outside the school"
        same = tools._same_place(tools._normalise_location(a), tools._normalise_location(b))
        result = score(report("R-1", location=a), [report("R-1", location=a), report("R-2", location=b)])
        self.assertEqual(result["factors"]["cluster"]["value"] == 2, same)

    def test_more_reports_raise_the_score_up_to_a_cap(self):
        def with_n(n):
            reports = [report(f"R-{i}") for i in range(n)]
            return score(reports[0], reports)["score"]
        self.assertGreater(with_n(2), with_n(1))
        self.assertEqual(with_n(priority.CLUSTER_CAP), with_n(priority.CLUSTER_CAP + 10))

    def test_no_location_is_never_a_cluster(self):
        for missing in (None, "", "Not given", "  "):
            target = report("R-1", location=missing)
            others = [target, report("R-2", location=missing), report("R-3", location=missing)]
            self.assertEqual(score(target, others)["factors"]["cluster"]["value"], 1, repr(missing))


class AgeTest(unittest.TestCase):
    def test_older_reports_rise(self):
        self.assertGreater(score(report(days=7))["score"], score(report(days=0))["score"])

    def test_very_old_reports_are_capped(self):
        capped = score(report(days=400))
        self.assertEqual(capped["score"], score(report(days=priority.AGE_CAP_DAYS))["score"])
        self.assertTrue(capped["factors"]["age_days"]["capped"])
        self.assertEqual(capped["factors"]["age_days"]["value"], 400)
        self.assertLessEqual(capped["factors"]["age_days"]["factor"], priority.AGE_MAX_FACTOR)
        self.assertIn("counted as 14", capped["explanation"])

    def test_age_alone_cannot_beat_severity_and_exposure(self):
        old_minor = score(report(category="noise_nuisance", severity="low", days=1000))
        new_serious = score(report(category="pothole", severity="high", days=0))
        self.assertGreater(new_serious["score"], old_minor["score"])

    def test_naive_timestamp_is_treated_as_utc(self):
        r = report()
        r["created_at"] = "2026-10-10T12:00:00"
        self.assertEqual(score(r)["factors"]["age_days"]["value"], 7)


class ResolvedTest(unittest.TestCase):
    def test_resolved_scores_zero_but_keeps_its_factors(self):
        result = score(report(status="resolved", days=30))
        self.assertEqual(result["score"], 0)
        self.assertEqual(set(result["factors"]), {"severity", "exposure", "cluster", "age_days"})
        self.assertIn("Resolved", result["explanation"])

    def test_in_review_still_scores(self):
        self.assertGreater(score(report(status="in_review"))["score"], 0)


class RangeTest(unittest.TestCase):
    def test_scores_stay_between_0_and_100(self):
        worst = [report(f"R-{i}", days=100) for i in range(10)]
        self.assertEqual(score(worst[0], worst)["score"], 100)
        mild = score(report(category="noise_nuisance", severity="low"))
        self.assertGreater(mild["score"], 0)
        self.assertLess(mild["score"], 100)

    def test_score_all_keys_by_id(self):
        reports = [report("R-1"), report("R-2", status="resolved")]
        scores = priority.score_all(reports, GROUPS, NOW)
        self.assertEqual(set(scores), {"R-1", "R-2"})
        self.assertEqual(scores["R-2"]["score"], 0)

    def test_pure_no_database(self):
        source = Path(priority.__file__).read_text(encoding="utf-8")
        self.assertNotIn("sqlite", source)
        self.assertNotIn("reports_db", source)


class CouncilPageTest(unittest.TestCase):
    def setUp(self):
        patch = unittest.mock.patch.object(tools._location_service, "forward_geocode", return_value=None)
        patch.start()
        self.addCleanup(patch.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.client = website.create_app(Path(self.tmp.name) / "p.db", "pw").test_client()
        self.auth = {"Authorization": "Basic " + base64.b64encode(b"officer:pw").decode()}

    def test_every_report_carries_score_factors_and_explanation(self):
        reports = self.client.get("/council/reports.json", headers=self.auth).get_json()["reports"]
        for r in reports:
            p = r["priority"]
            self.assertEqual(set(p["factors"]), {"severity", "exposure", "cluster", "age_days"})
            self.assertTrue(p["explanation"])
            if r["status"] == "resolved":
                self.assertEqual(p["score"], 0)

    def test_page_offers_priority_sort_and_shows_factors(self):
        html = self.client.get("/council", headers=self.auth).get_data(as_text=True)
        self.assertIn("Highest priority first", html)
        self.assertIn("factorLine", html)
        self.assertIn('"priority"', html)


if __name__ == "__main__":
    unittest.main(verbosity=2)

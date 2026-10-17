"""Tests for reports_db.py and tools.py. Standard library only.

Run:
  python code/test_tools.py
"""

import json
import sys
import tempfile
import unittest
import unittest.mock
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import reports_db
import tools

FAKE = json.loads(reports_db.FAKE_REPORTS_PATH.read_text(encoding="utf-8"))
BY_ID = {r["id"]: r for r in FAKE}
FLAGGED = [r for r in FAKE if r["duplicate_of"]]
# One known pair from the synthetic data: (original, repeat).
ORIGINAL, REPEAT = BY_ID[FLAGGED[0]["duplicate_of"]], FLAGGED[0]


def at(report, **delta):
    return datetime.fromisoformat(report["created_at"]) + timedelta(**delta)


class DbCase(unittest.TestCase):
    """Each test gets a fresh database seeded with the 68 synthetic reports."""

    def setUp(self):
        # save_report() geocodes the location via a real network call to
        # Nominatim. This class alone calls save_report dozens of times
        # across CheckDuplicateTest, SaveReportTest, GetReportStatusTest and
        # LocationAndStatusTest - without this mock every one of those would
        # hit the real network, making the suite slow, non-deterministic,
        # and inconsistent with every other test file in this repo, which
        # is deliberately network-free.
        self._geocode_patch = unittest.mock.patch.object(
            tools._location_service, "forward_geocode", return_value=None
        )
        self._geocode_patch.start()
        self.addCleanup(self._geocode_patch.stop)

        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "test.db"
        reports_db.init_db(self.path)
        self.conn = reports_db.connect(self.path)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def row(self, report_id):
        return self.conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()


class InitDbTest(DbCase):
    def test_loads_every_fake_report(self):
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0], len(FAKE))

    def test_is_idempotent(self):
        self.assertEqual(reports_db.init_db(self.path), len(FAKE))

    def test_empty_duplicate_of_becomes_null(self):
        self.assertIsNone(self.row(ORIGINAL["id"])["duplicate_of"])
        self.assertEqual(self.row(REPEAT["id"])["duplicate_of"], ORIGINAL["id"])


class FakeDataTest(unittest.TestCase):
    def test_nothing_is_dated_after_the_newest_original(self):
        newest = max(r["created_at"] for r in FAKE if not r["duplicate_of"])
        self.assertLessEqual(max(r["created_at"] for r in FAKE), newest)

    def test_repeats_point_at_open_originals(self):
        self.assertEqual(len(FLAGGED), 8)
        for report in FLAGGED:
            self.assertIn(BY_ID[report["duplicate_of"]]["status"], ("new", "in_review"), report["id"])


class FindCategoryFactsTest(unittest.TestCase):
    def test_pothole_has_rules_and_dated_sourced_facts(self):
        result = tools.find_category_facts("pothole")
        self.assertTrue(result["ok"])
        self.assertEqual(result["category"]["outcome"], "council_report")
        self.assertTrue(result["category"]["follow_up_questions"])
        self.assertIn("location_rule", result)
        self.assertTrue(result["facts"])
        for fact in result["facts"]:
            self.assertTrue(fact["url"].startswith("http"))
            self.assertEqual(fact["date_checked"], "2026-10-17")

    def test_multi_id_rows_reach_each_category(self):
        # The "urgent response aim" row is tagged fly_tipping; dog_fouling; ...
        for category_id in ("fly_tipping", "dog_fouling", "graffiti_flyposting"):
            topics = [f["topic"] for f in tools.find_category_facts(category_id)["facts"]]
            self.assertIn("Urgent response aim", topics, category_id)

    def test_hides_unconfirmed_team_and_synthetic_phrases(self):
        category = tools.find_category_facts("fly_tipping")["category"]
        for field in ("team", "team_confirmed", "example_phrases", "fms_categories"):
            self.assertNotIn(field, category)

    def test_not_council_gets_guidance_links(self):
        result = tools.find_category_facts("not_council_trunk_road")
        self.assertEqual(result["category"]["outcome"], "not_council")
        self.assertEqual(result["guidance_links"]["emergency"]["contact"], "999")

    def test_general(self):
        result = tools.find_category_facts("general")
        self.assertTrue(result["ok"])
        self.assertTrue(result["facts"])
        self.assertNotIn("category", result)

    def test_out_of_hours_numbers_are_confirmed_facts(self):
        url = "https://www.southampton.gov.uk/contact-us/emergency-out-of-hours/"
        facts = {f["topic"]: f for f in tools.find_category_facts("general")["facts"]}
        main = facts["Out-of-hours emergency number"]
        adult = facts["Out-of-hours adult social care number"]
        self.assertIn("023 8023 3344", main["fact"])
        self.assertIn("0300 555 1373", adult["fact"])
        self.assertNotIn("0300 555 1373", main["fact"])
        for fact in (main, adult):
            self.assertEqual((fact["url"], fact["date_checked"]), (url, "2026-10-17"))
        links = tools.find_category_facts("not_council_trunk_road")["guidance_links"]
        self.assertEqual(links["council_out_of_hours"]["contact"], "023 8023 3344")

    def test_no_wrong_number_and_no_road_ownership_claims(self):
        agent_dir = tools.AGENT_DIR
        for name in ("categories.json", "confirmed_with_websites.csv"):
            text = (agent_dir / name).read_text(encoding="utf-8")
            self.assertNotIn("8083 3344", text, name)
        note = tools.find_category_facts("not_council_trunk_road")["category"]["note"]
        self.assertIn("do not save a report", note)
        self.assertFalse(any("A33" in f["confirmed_fact"] or "A36" in f["confirmed_fact"]
                             for facts in tools._rulebook()[1].values() for f in facts))

    def test_utf8_survives(self):
        facts = tools.find_category_facts("illegal_parking")["facts"]
        self.assertTrue(any("£70" in f["fact"] for f in facts))

    def test_unknown_category(self):
        result = tools.find_category_facts("unicorns")
        self.assertFalse(result["ok"])
        self.assertIn("pothole", result["valid_ids"])


class CheckDuplicateTest(DbCase):
    def test_reproduces_every_flagged_duplicate_in_the_fake_data(self):
        # Remove each repeat first, so the match must come from the original alone.
        self.conn.execute(f"DELETE FROM reports WHERE id IN ({', '.join('?' * len(FLAGGED))})",
                          [r["id"] for r in FLAGGED])
        for report in FLAGGED:
            result = tools.check_duplicate(report["category_id"], report["location"],
                                           conn=self.conn, now=at(report))
            self.assertEqual(result["duplicate_of"], report["duplicate_of"], report["id"])
            self.assertEqual(result["matching_reports"], 1, report["id"])

    def test_finds_no_duplicates_the_fake_data_does_not_flag(self):
        for report in FAKE:
            if report["duplicate_of"] or report["status"] == "resolved":
                continue
            result = tools.check_duplicate(report["category_id"], report["location"],
                                           conn=self.conn, now=at(report))
            expected = 2 if any(r["duplicate_of"] == report["id"] for r in FLAGGED) else 1
            self.assertEqual(result["matching_reports"], expected, report["id"])

    def test_location_text_is_normalised(self):
        messy = "  " + REPEAT["location"].upper().replace(" ", "  ") + ". "
        result = tools.check_duplicate(REPEAT["category_id"], messy, conn=self.conn, now=at(REPEAT))
        self.assertTrue(result["is_duplicate"])

    def test_an_extra_word_is_the_same_place(self):
        first = tools.save_report("pothole", "Weston Lane", "Hole", conn=self.conn)
        result = tools.check_duplicate("pothole", "weston lane outside the school",
                                       conn=self.conn)
        self.assertTrue(result["is_duplicate"])
        self.assertEqual(result["duplicate_of"], first["report_id"])

    def test_a_directional_suffix_is_a_different_road(self):
        tools.save_report("pothole", "Weston Lane", "Hole", conn=self.conn)
        result = tools.check_duplicate("pothole", "Weston Lane North", conn=self.conn)
        self.assertFalse(result["is_duplicate"])

    def test_house_number_at_the_same_street_is_a_duplicate(self):
        tools.save_report("pothole", "Weston Lane", "Hole", conn=self.conn)
        result = tools.check_duplicate("pothole", "18 Weston Lane", conn=self.conn)
        self.assertTrue(result["is_duplicate"])

    def test_short_locations_never_match_by_containment(self):
        tools.save_report("pothole", "Mill", "Hole", conn=self.conn)
        result = tools.check_duplicate("pothole", "Mill Lane", conn=self.conn)
        self.assertFalse(result["is_duplicate"])


class SaveReportTest(DbCase):
    def test_saves_a_new_report(self):
        result = tools.save_report("pothole", "Weston Lane outside the school",
                                   "Deep pothole in the left lane", severity="high",
                                   has_photo=True, conn=self.conn)
        self.assertTrue(result["ok"])
        self.assertEqual(result["report_id"], "R-0069")
        self.assertEqual(len(result["link_token"]), 16)
        self.assertTrue(result["link"].endswith("/r/" + result["link_token"]))
        self.assertNotIn("R-0069", result["link"])
        self.assertIsNone(result["duplicate_of"])

        row = self.row("R-0069")
        self.assertEqual(row["status"], "new")
        self.assertEqual(row["severity"], "high")
        self.assertEqual(row["has_photo"], 1)
        self.assertEqual(row["link_token"], result["link_token"])
        datetime.fromisoformat(row["created_at"])

    def test_ids_increase_and_tokens_are_unique(self):
        a = tools.save_report("graffiti_flyposting", "Bargate", "Tag on the wall", conn=self.conn)
        b = tools.save_report("graffiti_flyposting", "Above Bar", "Posters", conn=self.conn)
        self.assertEqual((a["report_id"], b["report_id"]), ("R-0069", "R-0070"))
        self.assertNotEqual(a["link_token"], b["link_token"])

    def test_repeat_is_linked_to_the_original(self):
        first = tools.save_report("fly_tipping", "1 Test Street", "Sofa", conn=self.conn)
        second = tools.save_report("fly_tipping", "1 test street", "Sofa again", conn=self.conn)
        self.assertIsNone(first["duplicate_of"])
        self.assertEqual(second["duplicate_of"], first["report_id"])
        self.assertEqual(self.row(second["report_id"])["duplicate_of"], first["report_id"])

    def test_reporter_is_hashed_not_stored(self):
        result = tools.save_report("dead_animal", "Park Road", "Dead fox", reporter="+447700900123",
                                   conn=self.conn)
        ref = self.row(result["report_id"])["reporter_ref"]
        self.assertTrue(ref.startswith("h-"))
        self.assertNotIn("7700900123", ref)
        # The same sender gets the same ref, so the dashboard can group them.
        again = tools.save_report("dead_animal", "Hill Lane", "Dead pigeon", reporter="+447700900123",
                                  conn=self.conn)
        self.assertEqual(self.row(again["report_id"])["reporter_ref"], ref)

    def test_refuses_non_council_and_info_categories(self):
        for category_id in ("not_council_utility", "outside_southampton", "flooding_severe_weather"):
            result = tools.save_report(category_id, "Somewhere", "Something", conn=self.conn)
            self.assertFalse(result["ok"], category_id)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0], len(FAKE))

    def test_validates_input(self):
        self.assertFalse(tools.save_report("pothole", "", "hole", conn=self.conn)["ok"])
        self.assertFalse(tools.save_report("pothole", "Weston Lane", " ", conn=self.conn)["ok"])
        self.assertFalse(tools.save_report("pothole", "Weston Lane", "hole", severity="emergency",
                                           conn=self.conn)["ok"])
        self.assertFalse(tools.save_report("unicorns", "Weston Lane", "hole", conn=self.conn)["ok"])


class GetReportStatusTest(DbCase):
    def test_finds_a_fake_report_by_token(self):
        fake = next(r for r in FAKE if r["status"] == "resolved")
        result = tools.get_report_status(fake["link_token"], conn=self.conn)
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["status_text"], "marked as resolved")
        self.assertEqual(result["location"], fake["location"])

    def test_repeat_says_others_reported_it(self):
        result = tools.get_report_status(REPEAT["link_token"], conn=self.conn)
        self.assertTrue(result["reported_by_others_too"])

    def test_never_returns_the_id_or_reporter(self):
        result = tools.get_report_status(FAKE[0]["link_token"], conn=self.conn)
        self.assertNotIn("id", result)
        self.assertNotIn("reporter_ref", result)
        self.assertNotIn(FAKE[0]["id"], json.dumps(result))

    def test_round_trip_after_save(self):
        saved = tools.save_report("pothole", "Weston Lane", "Hole", conn=self.conn)
        result = tools.get_report_status(saved["link_token"], conn=self.conn)
        self.assertEqual(result["status"], "new")
        self.assertEqual(result["category"], tools.find_category_facts("pothole")["category"]["label"])

    def test_unknown_or_bad_token(self):
        for token in ("doesnotexist1234", "R-0001", "", None, "x" * 500):
            self.assertFalse(tools.get_report_status(token, conn=self.conn)["ok"], token)


class CallToolTest(unittest.TestCase):
    def test_schemas_cover_every_tool(self):
        names = [s["function"]["name"] for s in tools.tool_schemas()]
        self.assertEqual(sorted(names), sorted(tools.TOOLS))

    def test_json_string_arguments(self):
        result = tools.call_tool("find_category_facts", '{"category_id": "pothole"}')
        self.assertTrue(result["ok"])

    def test_bad_calls_return_errors_not_exceptions(self):
        self.assertFalse(tools.call_tool("drop_tables", {})["ok"])
        self.assertFalse(tools.call_tool("find_category_facts", "{not json")["ok"])
        self.assertFalse(tools.call_tool("find_category_facts", {})["ok"])
        # The model cannot set reporter or conn itself.
        self.assertFalse(tools.call_tool("save_report", {"category_id": "pothole", "location": "x",
                                                         "description": "y", "reporter": "spoof"})["ok"])


class LocationAndStatusTest(DbCase):
    def test_set_location_fills_a_missing_street(self):
        saved = tools.save_report("pothole", "Not given", "Hole", conn=self.conn)
        self.assertTrue(reports_db.set_location(self.conn, saved["report_id"], "Alma Road"))
        self.assertEqual(self.row(saved["report_id"])["location"], "Alma Road")

    def test_set_location_refuses_blank_or_not_given(self):
        saved = tools.save_report("pothole", "Not given", "Hole", conn=self.conn)
        self.assertFalse(reports_db.set_location(self.conn, saved["report_id"], "  "))
        self.assertFalse(reports_db.set_location(self.conn, saved["report_id"], "not given"))

    def test_latest_report_for_returns_the_newest(self):
        tools.save_report("pothole", "A Road", "Hole", conn=self.conn, reporter="+441")
        second = tools.save_report("fly_tipping", "B Road", "Sofa", conn=self.conn,
                                   reporter="+441")
        row = reports_db.latest_report_for(self.conn, tools.reporter_ref("+441"))
        self.assertEqual(row["id"], second["report_id"])

    def test_latest_report_for_unknown_is_none(self):
        self.assertIsNone(reports_db.latest_report_for(self.conn,
                                                       tools.reporter_ref("+449")))

    def test_link_duplicate_points_at_the_original(self):
        first = tools.save_report("pothole", "Alma Road", "Hole", conn=self.conn)
        second = tools.save_report("fly_tipping", "Cranbury Road", "Sofa", conn=self.conn)
        self.assertTrue(reports_db.link_duplicate(self.conn, second["report_id"],
                                                  first["report_id"]))
        self.assertEqual(self.row(second["report_id"])["duplicate_of"], first["report_id"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

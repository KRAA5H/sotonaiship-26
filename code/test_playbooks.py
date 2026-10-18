"""Tests for the generated playbooks. Offline, no network, no model.

Run: python code/test_playbooks.py
"""

import csv
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from services import build_playbooks as bp  # noqa: E402


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def rulebook():
    return read_json(bp.AGENT_DIR / "categories.json")


def fact_rows():
    path = bp.AGENT_DIR / "confirmed_with_websites.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def playbooks():
    return {path.stem: read_json(path) for path in bp.OUT_DIR.glob("*.json")
            if path.name != "_index.json"}


def index():
    return read_json(bp.OUT_DIR / "_index.json")


class FileSetTest(unittest.TestCase):
    def test_one_playbook_per_category_and_no_extras(self):
        categories = {item["id"] for item in rulebook()["categories"]}
        self.assertEqual(set(playbooks()), categories)
        self.assertEqual(len(playbooks()), 22)
        self.assertTrue((bp.OUT_DIR / "_index.json").exists())

    def test_check_is_current(self):
        self.assertEqual(bp.main(["--check"]), 0)

    def test_build_is_deterministic(self):
        self.assertEqual(bp.build(), bp.build())

    def test_drift_is_detected_in_a_temp_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            bp.write(tmp)
            self.assertEqual(bp.check(tmp), [])
            (Path(tmp) / "pothole.json").write_text("{}", encoding="utf-8")
            self.assertTrue(any("stale pothole" in item for item in bp.check(tmp)))
            (Path(tmp) / "extra.json").write_text("{}", encoding="utf-8")
            self.assertTrue(any("extra" in item for item in bp.check(tmp)))

    def test_source_files_are_not_changed(self):
        before = {name: hashlib.sha256((bp.AGENT_DIR / name).read_bytes()).hexdigest()
                  for name in ("categories.json", "confirmed_with_websites.csv")}
        bp.build()
        after = {name: hashlib.sha256((bp.AGENT_DIR / name).read_bytes()).hexdigest()
                 for name in before}
        self.assertEqual(before, after)


class PlaybookContractTest(unittest.TestCase):
    def test_required_local_is_in_the_draft_vocabulary(self):
        for name, item in playbooks().items():
            for field in item["required_local"]:
                self.assertIn(field, {"description", "location", "address"}, name)

    def test_capture_is_photo_or_description(self):
        for name, item in playbooks().items():
            self.assertEqual(set(item["required_capture_any"]),
                             {"description", "photo"}, name)

    def test_submission_is_honestly_unverified(self):
        for name, item in playbooks().items():
            self.assertEqual(item["required_submission"], [], name)
            self.assertEqual(item["submission_status"], "unverified", name)

    def test_no_team_is_confirmed(self):
        for name, item in playbooks().items():
            self.assertFalse(item["team_confirmed"], name)

    def test_specialist_groups_are_the_four(self):
        for name, item in playbooks().items():
            self.assertTrue(item["specialist_group"] is None
                            or item["specialist_group"] in bp.GROUP_ORDER, name)
        groups = index()["groups"]
        self.assertEqual(set(groups), set(bp.GROUP_ORDER))
        self.assertEqual(sum(len(ids) for ids in groups.values()), 12)

    def test_unclear_other_is_a_capture_playbook(self):
        item = playbooks()["unclear_other"]
        self.assertEqual(item["outcome"], "council_report")
        self.assertEqual(item["facts"], [])
        self.assertNotIn("unclear_other", index()["handoff_categories"])
        self.assertNotIn("unclear_other", index()["never_saved"])

    def test_required_detail_keeps_the_rulebook_fields(self):
        self.assertIn("road_name", playbooks()["pothole"]["required_detail"])
        self.assertIn("which_bin", playbooks()["missed_bin"]["required_detail"])
        self.assertIn("vehicle_registration_if_visible",
                      playbooks()["abandoned_vehicle"]["required_detail"])
        self.assertEqual(playbooks()["noise_nuisance"]["required_local"], [])

    def test_info_source_falls_back_to_answer_source(self):
        item = playbooks()["info_student_waste_rules"]
        self.assertTrue(item["source_url"].startswith("https://"))

    def test_duplicate_windows_have_a_fallback(self):
        self.assertEqual(playbooks()["pothole"]["duplicate_window_days"], 30)
        self.assertEqual(playbooks()["missed_bin"]["duplicate_window_days"], 7)
        self.assertEqual(playbooks()["info_student_waste_rules"]["duplicate_window_days"], 30)


class DataIntegrityTest(unittest.TestCase):
    def test_every_fact_row_is_covered(self):
        covered = set()
        for item in playbooks().values():
            for fact in item["facts"]:
                covered.add((fact["fact"], fact["url"]))
        known = {(row["confirmed_fact"], row["url"]) for row in fact_rows()
                 if row["category_id"] != "general"}
        self.assertEqual(covered, known)
        self.assertEqual(len(index()["general_fact_ids"]), 9)

    def test_known_facts_cover_every_url(self):
        urls = {row["url"] for row in fact_rows()}
        self.assertEqual(set(index()["known_facts"]), urls)

    def test_no_fact_is_invented(self):
        source = {(row["confirmed_fact"], row["url"], row["date_checked"])
                  for row in fact_rows()}
        for name, item in playbooks().items():
            for fact in item["facts"]:
                self.assertIn((fact["fact"], fact["url"], fact["date"]), source, name)

    def test_fact_ids_are_unique_contiguous_and_shared(self):
        ids = [f"F{index:03d}" for index in range(1, len(fact_rows()) + 1)]
        self.assertEqual(sorted(index()["fact_ids"]), ids)
        keys = [item["fact_key"] for item in index()["fact_ids"].values()]
        self.assertEqual(len(keys), len(set(keys)))
        seen = {}
        for name, item in playbooks().items():
            for fact in item["facts"]:
                marker = (fact["fact"], fact["url"])
                seen.setdefault(marker, set()).add(fact["id"])
        self.assertTrue(all(len(found) == 1 for found in seen.values()))

    def test_numbers_and_teams_are_available(self):
        numbers = set(index()["numbers"])
        for number in ("023 8023 3344", "0300 555 1373", "0300 123 5000"):
            self.assertIn(number, numbers)
        self.assertTrue(index()["teams"])

    def test_guidance_is_present(self):
        guidance = index()["guidance"]
        self.assertIn("emergency", guidance)
        self.assertIn("council_out_of_hours", guidance)
        by_category = index()["guidance_by_category"]
        self.assertIn("emergency",
                      by_category["flooding_severe_weather"]["show_guidance"])
        self.assertEqual(by_category["not_council_trunk_road"]["redirect_to"],
                         "national_highways")

    def test_two_dates_for_one_url_fail(self):
        rows = [{"url": "https://example.test/x", "date": "2026-10-17"},
                {"url": "https://example.test/x", "date": "2026-10-18"}]
        with self.assertRaises(ValueError):
            bp._known_facts(rows)


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""Tests for triage. No network: llm.chat is replaced.

Run: python code/test_triage.py
The six live messages are checked by `python code/triage.py`.
"""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import triage  # noqa: E402

GOOD = {
    "is_report": True,
    "category_id": "pothole",
    "location": "Weston Lane",
    "description": "Deep pothole outside the school",
    "severity": "high",
    "confidence": 0.9,
}


def fake(reply, mode="model"):
    return patch.object(triage.llm, "chat", return_value=(reply, mode))


class NormaliseTest(unittest.TestCase):
    def test_a_full_report_passes(self):
        decision = triage.normalise(GOOD)
        self.assertTrue(decision["is_report"])
        self.assertEqual(decision["reason"], "ok")
        self.assertEqual(decision["category_id"], "pothole")
        self.assertEqual(decision["severity"], "high")
        self.assertEqual(decision["confidence"], 0.9)

    def test_unknown_category_is_refused(self):
        decision = triage.normalise({**GOOD, "category_id": "meteor_strike"})
        self.assertFalse(decision["is_report"])
        self.assertEqual(decision["reason"], "unknown_category")
        self.assertIsNone(decision["category_id"])

    def test_missing_location_is_held_back(self):
        decision = triage.normalise({**GOOD, "location": "  "})
        self.assertFalse(decision["is_report"])
        self.assertEqual(decision["reason"], "no_location")

    def test_info_only_category_is_never_saved(self):
        decision = triage.normalise({**GOOD, "category_id": "info_student_waste_rules"})
        self.assertFalse(decision["is_report"])
        self.assertEqual(decision["reason"], "no_report_for_info_only")

    def test_out_of_area_is_never_saved(self):
        decision = triage.normalise({**GOOD, "category_id": "outside_southampton"})
        self.assertFalse(decision["is_report"])
        self.assertEqual(decision["reason"], "no_report_for_not_council")

    def test_model_saying_false_is_respected(self):
        decision = triage.normalise({**GOOD, "is_report": "false"})
        self.assertFalse(decision["is_report"])
        self.assertEqual(decision["reason"], "model_says_not_a_report")

    def test_bad_severity_is_dropped(self):
        self.assertIsNone(triage.normalise({**GOOD, "severity": "catastrophic"})["severity"])

    def test_confidence_is_clamped(self):
        self.assertEqual(triage.normalise({**GOOD, "confidence": 5})["confidence"], 1.0)
        self.assertEqual(triage.normalise({**GOOD, "confidence": -3})["confidence"], 0.0)
        self.assertEqual(triage.normalise({**GOOD, "confidence": "high"})["confidence"],
                         triage.CONFIDENCE_DEFAULT)

    def test_long_fields_are_capped(self):
        decision = triage.normalise({**GOOD, "description": "x" * 5000,
                                     "location": "y" * 500})
        self.assertLessEqual(len(decision["description"]), 400)
        self.assertLessEqual(len(decision["location"]), 120)

    def test_a_list_is_not_an_object(self):
        self.assertEqual(triage.normalise([GOOD])["reason"], "not_an_object")


class ParsingTest(unittest.TestCase):
    def test_plain_json(self):
        self.assertEqual(triage._raw_object(json.dumps(GOOD))["category_id"], "pothole")

    def test_fenced_json(self):
        raw = "```json\n" + json.dumps(GOOD) + "\n```"
        self.assertEqual(triage._raw_object(raw)["category_id"], "pothole")

    def test_json_surrounded_by_prose(self):
        raw = "Here you go: " + json.dumps(GOOD) + " hope that helps"
        self.assertEqual(triage._raw_object(raw)["category_id"], "pothole")

    def test_no_json_at_all(self):
        self.assertIsNone(triage._raw_object("I am afraid I cannot help with that."))


class TriageTest(unittest.TestCase):
    def test_parses_a_model_reply(self):
        with fake(json.dumps(GOOD)):
            decision = triage.triage("deep pothole on weston lane")
        self.assertTrue(decision["is_report"])

    def test_retries_once_then_succeeds(self):
        replies = [("not json", "model"), (json.dumps(GOOD), "model")]
        with patch.object(triage.llm, "chat", side_effect=replies) as chat:
            decision = triage.triage("deep pothole on weston lane")
        self.assertTrue(decision["is_report"])
        self.assertEqual(chat.call_count, 2)

    def test_two_bad_replies_give_up_cleanly(self):
        with patch.object(triage.llm, "chat", return_value=("nope", "model")):
            decision = triage.triage("deep pothole on weston lane")
        self.assertFalse(decision["is_report"])
        self.assertEqual(decision["reason"], "unparseable")
        self.assertEqual(decision["description"], "deep pothole on weston lane")

    def test_fallback_mode_is_not_a_report(self):
        with fake(triage.llm.STUB_REPLY, mode="fallback"):
            decision = triage.triage("anything")
        self.assertFalse(decision["is_report"])
        self.assertEqual(decision["reason"], "fallback")

    def test_a_photo_with_no_words_still_gets_a_prompt(self):
        with patch.object(triage.llm, "chat", return_value=(json.dumps(GOOD), "model")) as chat:
            triage.triage(None, image=(b"png", "image/png"))
        self.assertIn("photo", chat.call_args[0][1].lower())

    def test_text_is_capped_before_it_reaches_the_model(self):
        with patch.object(triage.llm, "chat", return_value=(json.dumps(GOOD), "model")) as chat:
            triage.triage("x" * 4000)
        self.assertLessEqual(len(chat.call_args[0][1]), triage.MAX_TEXT)

    def test_model_is_told_the_real_categories(self):
        system = triage._system()
        for category_id in triage.tools.category_ids():
            self.assertIn(category_id, system)


class GuidanceTest(unittest.TestCase):
    def test_council_report_gets_no_guidance(self):
        self.assertIsNone(triage.guidance_for("pothole"))

    def test_info_only_cites_a_fact(self):
        guidance = triage.guidance_for("info_student_waste_rules")
        self.assertTrue(guidance)
        self.assertIn("southampton.gov.uk", guidance)

    def test_not_council_points_somewhere(self):
        guidance = triage.guidance_for("not_council_trunk_road")
        self.assertTrue(guidance)
        self.assertIn("national highways", guidance.lower())

    def test_unknown_category_still_says_something(self):
        self.assertTrue(triage.guidance_for("no_such_category"))


if __name__ == "__main__":
    unittest.main(verbosity=2)

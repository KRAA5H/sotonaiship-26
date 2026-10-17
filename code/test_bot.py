"""Tests for the bot's reply copy and its follow-up memory. No network.

Run: python code/test_bot.py
"""

import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import blue_bubbles as bot  # noqa: E402


def decision(**fields):
    base = {
        "is_report": False,
        "category_id": "pothole",
        "category_label": "Pothole",
        "outcome": "council_report",
        "location": "",
        "description": "",
        "severity": None,
        "confidence": 0.5,
        "reason": "no_location",
    }
    base.update(fields)
    return base


class PendingLocationTest(unittest.TestCase):
    def setUp(self):
        bot._pending.clear()

    def tearDown(self):
        bot._pending.clear()

    def test_a_short_answer_joins_the_earlier_message(self):
        bot.remember_location("+441", "there is a pothole near my house")
        text, merged = bot.merge_pending("+441", "Alma Road, outside number 12")
        self.assertTrue(merged)
        self.assertIn("pothole near my house", text)
        self.assertIn("Alma Road", text)

    def test_the_answer_is_consumed_once(self):
        bot.remember_location("+441", "pothole somewhere")
        bot.merge_pending("+441", "Alma Road")
        _, merged = bot.merge_pending("+441", "Alma Road")
        self.assertFalse(merged)

    def test_a_different_person_does_not_borrow_the_memory(self):
        bot.remember_location("+441", "pothole somewhere")
        _, merged = bot.merge_pending("+442", "Alma Road")
        self.assertFalse(merged)

    def test_an_old_ask_expires(self):
        bot.remember_location("+441", "pothole somewhere")
        bot._pending["+441"] = ("pothole somewhere", time.time() - bot.PENDING_SECONDS - 5)
        _, merged = bot.merge_pending("+441", "Alma Road")
        self.assertFalse(merged)

    def test_a_long_message_is_not_treated_as_a_location(self):
        bot.remember_location("+441", "pothole somewhere")
        _, merged = bot.merge_pending("+441", "x" * 200)
        self.assertFalse(merged)

    def test_empty_text_is_not_merged(self):
        bot.remember_location("+441", "pothole somewhere")
        _, merged = bot.merge_pending("+441", "")
        self.assertFalse(merged)

    def test_the_memory_is_bounded(self):
        for index in range(bot.PENDING_LIMIT + 20):
            bot.remember_location(f"+44{index}", "pothole")
        self.assertLessEqual(len(bot._pending), bot.PENDING_LIMIT)


class ReplyCopyTest(unittest.TestCase):
    def test_missing_location_asks_for_one(self):
        reply = bot.reply_for(decision(reason="no_location"), "+441")
        self.assertIn("where", reply.lower())
        self.assertIn("landmark", reply.lower())

    def test_out_of_area_mentions_nothing_was_logged(self):
        reply = bot.reply_for(decision(reason="no_report_for_not_council",
                                       category_id="not_council_trunk_road",
                                       category_label="Motorway or trunk road problem"), "+441")
        self.assertIn("nothing has been logged", reply.lower())

    def test_a_photo_that_is_not_a_council_issue_says_what_was_seen(self):
        reply = bot.reply_for(decision(reason="model_says_not_a_report",
                                       description="a bag of biscuits on a desk"),
                              "+441", has_photo=True)
        self.assertIn("bag of biscuits", reply)
        self.assertIn("nothing has been logged", reply.lower())

    def test_a_photo_description_prefix_is_not_repeated(self):
        reply = bot.reply_for(decision(reason="model_says_not_a_report",
                                       description="Photo shows a bag of biscuits on a desk"),
                              "+441", has_photo=True)
        self.assertNotIn("From your photo: Photo shows", reply)
        self.assertIn("From your photo: a bag of biscuits", reply)

    def test_unreadable_message_asks_again_without_guessing(self):
        reply = bot.reply_for(decision(reason="unparseable", category_id=None), "+441")
        self.assertIn("did not catch that", reply.lower())

    def test_a_saved_report_reply_carries_one_link(self):
        saved = {"ok": True, "report_id": "R-0400", "link": "http://host/r/token1",
                 "duplicate_of": None, "matching_reports": 0}
        with patch.object(bot.tools, "save_report", return_value=saved):
            reply = bot.reply_for(decision(reason="ok", is_report=True,
                                           location="Alma Road"), "+441")
        self.assertEqual(reply.count("http"), 1)
        self.assertIn("Pothole", reply)
        self.assertNotIn("R-0400", reply)  # the internal id never goes to a resident

    def test_a_duplicate_points_at_the_original(self):
        saved = {"ok": True, "report_id": "R-0401", "link": "http://host/r/token2",
                 "duplicate_of": "R-0400", "matching_reports": 1}
        with patch.object(bot.tools, "save_report", return_value=saved):
            reply = bot.reply_for(decision(reason="ok", is_report=True,
                                           location="Alma Road"), "+441")
        self.assertIn("already open", reply)
        self.assertIn("http://host/r/token2", reply)

    def test_a_refused_save_apologises_instead_of_claiming_success(self):
        with patch.object(bot.tools, "save_report",
                          return_value={"ok": False, "error": "no location"}):
            reply = bot.reply_for(decision(reason="ok", is_report=True,
                                           location="Alma Road"), "+441")
        self.assertIn("could not log", reply.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)

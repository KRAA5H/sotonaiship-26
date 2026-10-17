"""Tests for the bot's reply paths and its follow-up memory. No network, no database.

Run: python code/test_bot.py
"""

import sys
import time
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import blue_bubbles as bot  # noqa: E402
import messages  # noqa: E402

SAVED = {"ok": True, "report_id": "R-0100", "link": "http://host/r/token1",
         "duplicate_of": None, "matching_reports": 0}


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

    def test_the_incomplete_report_is_remembered(self):
        bot.remember_location("+441", "pothole near my house", SAVED, decision())
        entry = bot._pending["+441"]
        self.assertEqual(entry["report_id"], "R-0100")
        self.assertEqual(entry["link"], SAVED["link"])
        self.assertEqual(entry["category_id"], "pothole")

    def test_a_short_answer_joins_the_earlier_message(self):
        bot.remember_location("+441", "there is a pothole near my house", SAVED, decision())
        text, entry = bot.merge_pending("+441", "Alma Road, outside number 12")
        self.assertIn("pothole near my house", text)
        self.assertIn("Alma Road", text)
        self.assertEqual(entry["report_id"], "R-0100")

    def test_the_answer_is_consumed_once(self):
        bot.remember_location("+441", "pothole somewhere", SAVED, decision())
        bot.merge_pending("+441", "Alma Road")
        _, entry = bot.merge_pending("+441", "Alma Road")
        self.assertIsNone(entry)

    def test_a_different_person_does_not_borrow_the_memory(self):
        bot.remember_location("+441", "pothole somewhere", SAVED, decision())
        _, entry = bot.merge_pending("+442", "Alma Road")
        self.assertIsNone(entry)

    def test_an_old_ask_expires(self):
        bot.remember_location("+441", "pothole somewhere", SAVED, decision())
        bot._pending["+441"]["asked_at"] = time.time() - bot.PENDING_SECONDS - 5
        _, entry = bot.merge_pending("+441", "Alma Road")
        self.assertIsNone(entry)

    def test_a_long_message_is_not_treated_as_a_location(self):
        bot.remember_location("+441", "pothole somewhere", SAVED, decision())
        _, entry = bot.merge_pending("+441", "x" * 200)
        self.assertIsNone(entry)

    def test_empty_text_is_not_merged(self):
        bot.remember_location("+441", "pothole somewhere", SAVED, decision())
        _, entry = bot.merge_pending("+441", "")
        self.assertIsNone(entry)

    def test_the_memory_is_bounded(self):
        for index in range(bot.PENDING_LIMIT + 20):
            bot.remember_location(f"+44{index}", "pothole", SAVED, decision())
        self.assertLessEqual(len(bot._pending), bot.PENDING_LIMIT)


class ActFirstTest(unittest.TestCase):
    def setUp(self):
        bot._pending.clear()

    def tearDown(self):
        bot._pending.clear()

    def test_a_missing_street_still_logs_the_report(self):
        with unittest.mock.patch.object(bot.tools, "save_report", return_value=SAVED) as save:
            reply = bot.reply_for(decision(reason="no_location", location=""),
                                  "+441", "there is a pothole near my house")
        self.assertEqual(save.call_args.kwargs["location"], "Not given")
        self.assertIn("?", reply)
        self.assertEqual(bot._pending["+441"]["report_id"], "R-0100")

    def test_the_answer_fills_in_the_street_instead_of_saving_again(self):
        entry = {"text": "pothole near my house", "asked_at": time.time(),
                 "report_id": "R-0100", "link": SAVED["link"], "category_id": "pothole"}
        with unittest.mock.patch.object(bot.reports_db, "set_location",
                                        return_value=True) as moved, \
             unittest.mock.patch.object(bot.tools, "save_report") as save:
            reply = bot.reply_for(decision(reason="ok", location="Alma Road"),
                                  "+441", "merged text", pending=entry)
        moved.assert_called_once()
        self.assertIn("Alma Road", moved.call_args.args[2])
        save.assert_not_called()
        self.assertIn(SAVED["link"], reply)
        self.assertIn("Logged:", reply)

    def test_a_different_category_on_the_follow_up_is_a_new_report(self):
        entry = {"text": "pothole near my house", "asked_at": time.time(),
                 "report_id": "R-0100", "link": SAVED["link"], "category_id": "pothole"}
        with unittest.mock.patch.object(bot.reports_db, "set_location") as moved, \
             unittest.mock.patch.object(bot.tools, "save_report", return_value=SAVED):
            bot.reply_for(decision(reason="ok", category_id="fly_tipping",
                                   category_label="Fly-tipping", location="Alma Road"),
                          "+441", "merged text", pending=entry)
        moved.assert_not_called()

    def test_a_failed_move_falls_back_to_saving(self):
        entry = {"text": "pothole", "asked_at": time.time(),
                 "report_id": "R-0100", "link": SAVED["link"], "category_id": "pothole"}
        with unittest.mock.patch.object(bot.reports_db, "set_location", return_value=False), \
             unittest.mock.patch.object(bot.tools, "save_report", return_value=SAVED) as save:
            bot.reply_for(decision(reason="ok", location="Alma Road"),
                          "+441", "merged", pending=entry)
        save.assert_called_once()

    def test_a_refused_save_still_asks_for_the_street(self):
        with unittest.mock.patch.object(bot.tools, "save_report",
                                        return_value={"ok": False, "error": "no"}):
            reply = bot.reply_for(decision(reason="no_location"), "+441", "text")
        self.assertIn("?", reply)
        self.assertNotIn("+441", bot._pending)


class ReplyCopyTest(unittest.TestCase):
    def test_a_saved_report_reply_carries_one_link_and_no_internal_id(self):
        with unittest.mock.patch.object(bot.tools, "save_report", return_value=SAVED):
            reply = bot.reply_for(decision(reason="ok", location="Alma Road"), "+441")
        self.assertEqual(reply.count("http"), 1)
        self.assertIn("Logged: pothole, Alma Road.", reply)
        self.assertNotIn("R-0100", reply)

    def test_a_duplicate_points_at_the_original(self):
        saved = {**SAVED, "duplicate_of": "R-0069"}
        with unittest.mock.patch.object(bot.tools, "save_report", return_value=saved):
            reply = bot.reply_for(decision(reason="ok", location="Alma Road"), "+441")
        self.assertIn("Already logged", reply)
        self.assertIn(SAVED["link"], reply)

    def test_out_of_scope_uses_the_official_contact(self):
        reply = bot.reply_for(
            decision(reason="no_report_for_not_council", outcome="not_council",
                     category_id="not_council_trunk_road",
                     category_label="Motorway or trunk road problem"), "+441")
        self.assertIn("National Highways", reply)
        self.assertNotIn("google.com", reply)

    def test_a_photo_that_is_not_a_council_issue_says_what_was_seen(self):
        reply = bot.reply_for(decision(reason="model_says_not_a_report",
                                       description="Photo shows a bag of biscuits on a desk"),
                              "+441", has_photo=True)
        self.assertIn("bag of biscuits", reply)
        self.assertNotIn("From your photo: Photo shows", reply)

    def test_an_unreadable_message_asks_again(self):
        self.assertEqual(bot.reply_for(decision(reason="unparseable"), "+441"),
                         messages.unclear())

    def test_thanks_would_be_silence(self):
        self.assertEqual(messages.thanks(), "")


class StatusTest(unittest.TestCase):
    def test_status_questions_are_recognised(self):
        for text in ("any update?", "what is the status", "any news",
                     "is it fixed", "any progress", "heard anything back"):
            self.assertTrue(bot.wants_status(text), text)

    def test_a_report_is_not_a_status_question(self):
        for text in ("there is a pothole on Alma Road",
                     "fly tipping on the corner", ""):
            self.assertFalse(bot.wants_status(text), text)

    def test_a_long_message_is_not_a_status_question(self):
        self.assertFalse(bot.wants_status("update " + "x" * 130))

    def test_status_reply_uses_the_latest_report(self):
        report = {"id": "R-0070", "category_id": "pothole", "status": "in_review",
                  "status_text": "being looked at by the council",
                  "location": "Weston Lane", "link_token": "tok"}
        with unittest.mock.patch.object(bot.reports_db, "connect"),              unittest.mock.patch.object(bot.reports_db, "latest_report_for",
                                        return_value=report):
            got = bot.status_reply("+441")
        self.assertIn("being looked at by the council", got[1])
        self.assertIn("/r/tok", got[1])

    def test_no_report_means_no_status_reply(self):
        with unittest.mock.patch.object(bot.reports_db, "connect"),              unittest.mock.patch.object(bot.reports_db, "latest_report_for",
                                        return_value=None):
            self.assertIsNone(bot.status_reply("+441"))

    def test_a_returning_report_is_linked_to_the_old_one(self):
        with unittest.mock.patch.object(bot.reports_db, "connect"),              unittest.mock.patch.object(bot.tools, "save_report", return_value=SAVED),              unittest.mock.patch.object(bot.reports_db, "link_duplicate") as link:
            bot.reply_for(decision(reason="ok", location="Alma Road"), "+441",
                          relink_to="R-0069")
        link.assert_called_once()


class ConversationTest(unittest.TestCase):
    def test_thanks_and_acknowledgements_are_silence(self):
        for text in ("thanks", "thank you", "cheers", "ok", "great!"):
            self.assertTrue(bot.wants_silence(text), text)

    def test_a_thanks_with_a_new_report_is_not_silence(self):
        self.assertFalse(bot.wants_silence("great, there is a pothole on Alma Road"))

    def test_greetings_are_recognised(self):
        for text in ("hi", "hello", "hey!", "good morning", "hello there"):
            self.assertTrue(bot.wants_greeting(text), text)

    def test_a_greeting_with_a_report_is_not_a_greeting(self):
        self.assertFalse(bot.wants_greeting("hi, pothole on Alma Road"))

    def test_questions_are_recognised(self):
        for text in ("how long does it take?", "what happens next", "who fixes the motorway?"):
            self.assertTrue(bot.is_question(text), text)
        self.assertFalse(bot.is_question("pothole on Alma Road"))

    def test_an_information_question_gets_the_grounded_answer(self):
        with unittest.mock.patch.object(bot.rag, "answer",
                                        return_value=("Two weeks." + chr(10)*2
                                                       + "Source: X, checked 2026-10-17", [{}])):
            reply = bot.reply_for(decision(reason="model_says_not_a_report",
                                           category_id="council_service_other"),
                                  "+441", "how long does a pothole take?")
        self.assertIn("Source:", reply)

    def test_no_checked_answer_falls_back_to_the_official_page(self):
        with unittest.mock.patch.object(bot.rag, "answer", return_value=("", [])):
            reply = bot.reply_for(decision(reason="model_says_not_a_report",
                                           category_id="council_service_other"),
                                  "+441", "how do I get a parking permit?")
        self.assertIn("I do not have a checked answer", reply)

    def test_an_out_of_area_question_never_reaches_retrieval(self):
        with unittest.mock.patch.object(bot.rag, "answer") as rag_answer:
            bot.reply_for(decision(reason="no_report_for_not_council", outcome="not_council",
                                   category_id="not_council_trunk_road"),
                          "+441", "who fixes the motorway?")
        rag_answer.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)

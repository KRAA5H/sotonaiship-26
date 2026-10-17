"""Tests for the bot's reply paths and its follow-up memory. No network, no database.

Run: python code/test_bot.py
"""

import sys
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import blue_bubbles as bot  # noqa: E402
import messages  # noqa: E402

_patches = []


def setUpModule():
    """Templates are the fallback contract: keep the suite offline by default.

    The location agent's map link writes the pin database; these tests check
    the words, so it is stubbed (test_agents.py covers the link itself).
    """
    _patches.append(unittest.mock.patch.object(bot.voice, "generate", return_value=None))
    _patches.append(unittest.mock.patch.object(bot.ORCHESTRATOR.location, "map_link", return_value=None))
    for patch in _patches:
        patch.start()


def tearDownModule():
    for patch in _patches:
        patch.stop()

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

    def test_an_unknown_answer_offers_help_before_the_page(self):
        with unittest.mock.patch.object(bot.rag, "answer", return_value=("", [])):
            reply = bot.reply_for(decision(reason="model_says_not_a_report",
                                           category_id="council_service_other"),
                                  "+441", "how do I get a parking permit?")
        self.assertIn("I can help with that", reply)

    def test_an_out_of_area_question_never_reaches_retrieval(self):
        with unittest.mock.patch.object(bot.rag, "answer") as rag_answer:
            bot.reply_for(decision(reason="no_report_for_not_council", outcome="not_council",
                                   category_id="not_council_trunk_road"),
                          "+441", "who fixes the motorway?")
        rag_answer.assert_not_called()


class VoiceIntegrationTest(unittest.TestCase):
    def test_a_compliant_voiced_reply_is_used_and_carries_the_link(self):
        voiced = ("nice one, that's logged - pothole on Weston Lane. "
                  "if you can grab a photo, send it over.")
        with unittest.mock.patch.object(bot.voice, "generate", return_value=voiced),              unittest.mock.patch.object(bot.tools, "save_report", return_value=SAVED):
            reply = bot.reply_for(decision(reason="ok", location="Weston Lane"), "+441")
        self.assertIn("nice one, that's logged", reply)
        self.assertIn(SAVED["link"], reply)

    def test_a_corporate_voiced_reply_falls_back_to_the_template(self):
        bad = "Please be advised that the pothole on Weston Lane has been logged."
        with unittest.mock.patch.object(bot.voice, "generate", return_value=bad),              unittest.mock.patch.object(bot.tools, "save_report", return_value=SAVED):
            reply = bot.reply_for(decision(reason="ok", location="Weston Lane"), "+441")
        self.assertNotIn("Please be advised", reply)
        self.assertEqual(reply, messages.logged(decision(reason="ok", location="Weston Lane"),
                                                SAVED))

    def test_an_invented_timescale_falls_back(self):
        bad = "Logged, pothole on Weston Lane, a crew will be out within 2 hours."
        with unittest.mock.patch.object(bot.voice, "generate", return_value=bad),              unittest.mock.patch.object(bot.tools, "save_report", return_value=SAVED):
            reply = bot.reply_for(decision(reason="ok", location="Weston Lane"), "+441")
        self.assertNotIn("2 hours", reply)


class LatePhotoTest(unittest.TestCase):
    def setUp(self):
        bot._pending.clear()

    def tearDown(self):
        bot._pending.clear()

    def _report(self, report_id="R-0300", hours_ago=0):
        created = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
        return {"id": report_id, "created_at": created, "category_id": "pothole",
                "location": "Alma Road", "link_token": "tok" + report_id}

    def test_one_recent_open_report_receives_the_photo(self):
        with unittest.mock.patch.object(bot.reports_db, "connect"),              unittest.mock.patch.object(bot.reports_db, "open_reports_for",
                                        return_value=[self._report()]),              unittest.mock.patch.object(bot.reports_db, "set_photo",
                                        return_value=True) as set_photo:
            got = bot.attach_photo_to_open_report(
                "+443", {"guid": "G-1", "mimeType": "image/jpeg"}, (b"x", "image/jpeg"))
        self.assertEqual(got["report_id"], "R-0300")
        self.assertIn("/r/tokR-0300", got["link"])
        set_photo.assert_called_once()

    def test_two_open_reports_is_not_a_guess(self):
        with unittest.mock.patch.object(bot.reports_db, "connect"),              unittest.mock.patch.object(bot.reports_db, "open_reports_for",
                                        return_value=[self._report("R-1"),
                                                      self._report("R-2")]),              unittest.mock.patch.object(bot.reports_db, "set_photo") as set_photo:
            got = bot.attach_photo_to_open_report(
                "+443", {"guid": "G-1", "mimeType": "image/jpeg"}, (b"x", "image/jpeg"))
        self.assertIsNone(got)
        set_photo.assert_not_called()

    def test_an_old_report_is_not_matched(self):
        with unittest.mock.patch.object(bot.reports_db, "connect"),              unittest.mock.patch.object(bot.reports_db, "open_reports_for",
                                        return_value=[self._report(hours_ago=100)]),              unittest.mock.patch.object(bot.reports_db, "set_photo") as set_photo:
            got = bot.attach_photo_to_open_report(
                "+443", {"guid": "G-1", "mimeType": "image/jpeg"}, (b"x", "image/jpeg"))
        self.assertIsNone(got)
        set_photo.assert_not_called()

    def test_a_pending_report_wins_over_the_lookup(self):
        bot.remember_location("+444", "pothole", SAVED, decision())
        with unittest.mock.patch.object(bot.reports_db, "connect"),              unittest.mock.patch.object(bot.reports_db, "open_reports_for") as lookup,              unittest.mock.patch.object(bot.reports_db, "set_photo", return_value=True):
            got = bot.attach_photo_to_open_report(
                "+444", {"guid": "G-2", "mimeType": "image/jpeg"}, (b"x", "image/jpeg"))
        self.assertEqual(got["report_id"], "R-0100")
        lookup.assert_not_called()

    def test_the_maps_payload_is_never_a_photo(self):
        self.assertFalse(bot._is_image_attachment(
            {"transferName": "abc.pluginPayloadAttachment", "mimeType": None}))
        self.assertTrue(bot._is_image_attachment(
            {"transferName": "images.jpeg", "mimeType": "image/jpeg"}))


class BurstTest(unittest.TestCase):
    def setUp(self):
        with bot._burst_lock:
            for entry in bot._burst.values():
                if entry.get("timer"):
                    entry["timer"].cancel()
            bot._burst.clear()

    def tearDown(self):
        self.setUp()

    def _message(self, sender, text="", attachments=None):
        return {"sender": sender, "chat_guid": "any;-;" + sender, "text": text,
                "attachments": attachments or []}

    def test_two_quick_messages_become_one_turn(self):
        with unittest.mock.patch.object(bot, "handle_inbound") as handler:
            bot.enqueue_message(self._message("+451", "there is a pothole"))
            bot.enqueue_message(self._message("+451", "on weston lane"))
            bot.flush_burst("+451")
        handler.assert_called_once()
        inbound = handler.call_args.args[0]
        self.assertIn("pothole", inbound["text"])
        self.assertIn("weston lane", inbound["text"])

    def test_two_senders_never_merge(self):
        with unittest.mock.patch.object(bot, "handle_inbound") as handler:
            bot.enqueue_message(self._message("+451", "one"))
            bot.enqueue_message(self._message("+452", "two"))
            bot.flush_burst("+451")
            self.assertEqual(handler.call_args.args[0]["text"], "one")
            bot.flush_burst("+452")
            self.assertEqual(handler.call_args.args[0]["text"], "two")

    def test_attachments_are_kept_with_the_burst(self):
        with unittest.mock.patch.object(bot, "handle_inbound") as handler:
            bot.enqueue_message(self._message("+451", "see this",
                                              [{"guid": "G-1", "mimeType": "image/jpeg"}]))
            bot.flush_burst("+451")
        self.assertEqual(handler.call_args.args[0]["attachments"][0]["guid"], "G-1")

    def test_a_late_message_can_be_taken_before_the_timer(self):
        bot.enqueue_message(self._message("+451", "first"))
        late = bot.take_pending("+451")
        self.assertEqual(late["texts"], ["first"])
        self.assertIsNone(bot.take_pending("+451"))


    def test_a_long_follow_up_does_not_lose_the_report(self):
        bot.remember_location("+451", "pothole somewhere", SAVED, decision())
        text, entry = bot.merge_pending("+451", "x" * 200)
        self.assertIsNone(entry)
        self.assertIn("+451", bot._pending)

    def test_a_message_during_a_turn_never_runs_a_second_turn(self):
        calls = []

        def slow(inbound):
            calls.append(inbound["text"])
            time.sleep(0.3)

        with unittest.mock.patch.object(bot, "handle_inbound", side_effect=slow):
            bot.enqueue_message(self._message("+451", "first"))
            worker = threading.Thread(target=bot.flush_burst, args=("+451",))
            worker.start()
            time.sleep(0.05)
            bot.enqueue_message(self._message("+451", "second"))
            worker.join()
        self.assertEqual(calls, ["first"])
        self.assertEqual(bot._burst["+451"]["texts"], ["second"])

    def test_an_empty_burst_does_nothing(self):
        with unittest.mock.patch.object(bot, "handle_inbound") as handler:
            bot.flush_burst("nobody")
        handler.assert_not_called()


class LinkDeliveryTest(unittest.TestCase):
    def test_the_words_and_the_link_are_two_messages(self):
        body, link = bot.split_reply(
            "Logged: pothole, Alma Road.\nThe council has it for review.\n"
            "Follow it: https://example.test/r/tok")
        self.assertEqual(body, "Logged: pothole, Alma Road.\nThe council has it for review.")
        self.assertEqual(link, "https://example.test/r/tok")

    def test_a_link_only_reply_is_just_the_link(self):
        self.assertEqual(bot.split_reply("https://example.test/r/tok"),
                         ("", "https://example.test/r/tok"))

    def test_no_link_means_one_message(self):
        self.assertEqual(bot.split_reply("hello there"), ("hello there", ""))

    def test_deliver_sends_the_link_after_the_words(self):
        with unittest.mock.patch.object(bot.bb, "send_text") as send, \
             unittest.mock.patch.object(bot.time, "sleep") as sleep:
            bot.deliver("chat", "Logged: pothole.\nFollow it: https://example.test/r/tok")
        self.assertEqual([call.args[1] for call in send.call_args_list],
                         ["Logged: pothole.", "https://example.test/r/tok"])
        sleep.assert_called_once()


class PlaceTest(unittest.TestCase):
    def setUp(self):
        bot._places.clear()

    def tearDown(self):
        bot._places.clear()

    def _service(self):
        class Fake:
            def reverse_geocode(self, latitude, longitude):
                return {"street_name": "Highfield Road", "postcode": "SO17 1BJ",
                        "area": "Highfield", "latitude": latitude,
                        "longitude": longitude}
        return Fake()

    def test_a_maps_link_becomes_a_street(self):
        with unittest.mock.patch.object(bot.location, "LocationService",
                                        side_effect=self._service):
            place = bot.place_from_text(
                "https://maps.apple.com/place?coordinate=50.9097,-1.4044&name=x")
        self.assertEqual(place["street_name"], "Highfield Road")

    def test_a_pin_fills_a_missing_location(self):
        filled = bot.apply_place(
            {"category_id": "pothole", "outcome": "council_report",
             "reason": "no_location", "location": "", "is_report": False},
            {"street_name": "Highfield Road"})
        self.assertEqual(filled["location"], "Highfield Road")
        self.assertEqual(filled["reason"], "ok")
        self.assertTrue(filled["is_report"])

    def test_a_pin_never_overwrites_a_street_the_resident_gave(self):
        kept = bot.apply_place(
            {"category_id": "pothole", "outcome": "council_report",
             "reason": "ok", "location": "Alma Road"},
            {"street_name": "Highfield Road"})
        self.assertEqual(kept["location"], "Alma Road")

    def test_a_pin_is_used_once(self):
        bot.remember_place("+451", {"street_name": "Highfield Road"})
        self.assertEqual(bot.take_place("+451")["street_name"], "Highfield Road")
        self.assertIsNone(bot.take_place("+451"))


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""Tests for the resident's voice. No network, no database, no model.

Every lint rule in the plan is an assertion here. The model is always faked, so
the suite says what a bad reply may not do rather than what a good one happens
to say today.

Run: python code/test_voice.py
"""

import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import voice  # noqa: E402

BOOK = json.loads((Path(voice.AGENT_DIR) / "categories.json").read_text(encoding="utf-8"))
CATEGORY_IDS = [category["id"] for category in BOOK["categories"]]
LINK = "http://192.168.0.202:5005/r/token123"

SAVED = {"category_id": "pothole", "category_label": "Pothole",
         "location": "Weston Lane", "has_photo": False, "group": "roads_and_parking"}
DUPLICATE = {"category_id": "pothole", "location": "Weston Lane"}
INCOMPLETE = {"category_id": "pothole"}
NOT_COUNCIL = {"category_id": "not_council_trunk_road",
               "org": "National Highways", "contact": "0300 123 5000"}
NO_ANSWER = {"category_id": "council_service_other",
             "page": "https://www.southampton.gov.uk/contact-us/online-forms"}
STATUS = {"category_id": "pothole", "location": "Weston Lane",
          "status_text": "being looked at by the council"}

# One reply per kind that a good model could send, and that must pass lint.
# (name, kind, facts, text); saved appears twice, with and without a photo.
GOOD = (
    ("saved", "saved", SAVED,
     "nice one, that's logged - pothole on Weston Lane. if you can grab a photo, send it "
     "over and it'll help the crew."),
    ("saved_photo", "saved", {**SAVED, "has_photo": True},
     "nice one, that's logged - pothole on Weston Lane. the photo helps, so you're all set."),
    ("duplicate", "duplicate", DUPLICATE,
     "someone's already reported that one, so i've linked yours to it - pothole on Weston "
     "Lane. if you can grab a photo, send it over."),
    ("incomplete", "incomplete", INCOMPLETE,
     "got it, pothole logged. whereabouts is it? a street and the nearest number is plenty. "
     "if you can grab a photo, send it over."),
    ("not_council", "not_council", NOT_COUNCIL,
     "ah that one's not ours, sorry. National Highways handles motorways, so give them a "
     "ring on 0300 123 5000."),
    ("no_answer", "no_answer", NO_ANSWER,
     "i can help with that - tell me a bit more and i'll point you the right way."),
    ("unclear", "unclear", {},
     "sorry, i didn't catch that. tell me what the problem is and which street."),
    ("greeting", "greeting", {},
     "hello. send me a street problem and i'll get it logged."),
    ("status", "status", STATUS,
     "quick update on the pothole at Weston Lane - it's being looked at by the council now."),
    ("photo_added", "photo_added", {"category_id": "pothole"},
     "got your photo for the pothole report, thanks. that'll help whoever picks it up."),
    ("photo_not_report", "photo_not_report", {},
     "ah that's not something the council can act on, so nothing's been logged."),
    ("emergency", "emergency", {"contact": "999"},
     "Call 999 now. Tell them where it is, and reply here if it's safe."),
)
GOOD_BY_NAME = {name: (kind, facts, text) for name, kind, facts, text in GOOD}

BAD_TEMPLATE = "Logged: pothole, Weston Lane.\nThe council has it for review.\nFollow it: " + LINK


def fake_chat(*responses):
    """A stand-in for llm.chat that replays responses and records the calls."""
    replies = list(responses)
    calls = []

    def chat(system, user, image=None, max_tokens=None, temperature=None):
        calls.append({"system": system, "user": user, "max_tokens": max_tokens,
                      "temperature": temperature})
        value = replies.pop(0) if len(replies) > 1 else replies[0]
        if isinstance(value, Exception):
            raise value
        return value

    chat.calls = calls
    return chat


def spoken(text):
    """A model reply carrying one message."""
    return (json.dumps({"text": text}), "model")


class SpokenNameTest(unittest.TestCase):
    def test_every_category_has_a_spoken_name(self):
        for category_id in CATEGORY_IDS:
            name = voice.speak_name(category_id)
            self.assertTrue(name, category_id)
            self.assertEqual(name, name.lower(), category_id)
            self.assertNotIn("_", name, category_id)
            self.assertNotIn("/", name, category_id)

    def test_the_alias_map_covers_the_rulebook_exactly(self):
        self.assertEqual(set(voice.SPOKEN_NAMES), set(CATEGORY_IDS))

    def test_the_names_a_person_would_actually_say(self):
        expected = {
            "pothole": "pothole",
            "fly_tipping": "fly-tipping",
            "litter_street_cleaning": "litter",
            "noise_nuisance": "noise complaint",
            "missed_bin": "bin collection",
            "council_housing_repair": "repair",
            "abandoned_vehicle": "abandoned car",
        }
        for category_id, name in expected.items():
            self.assertEqual(voice.speak_name(category_id), name)

    def test_an_unknown_category_falls_back(self):
        self.assertEqual(voice.speak_name("something_new"), voice.FALLBACK_SPOKEN)
        self.assertEqual(voice.speak_name(None), voice.FALLBACK_SPOKEN)


class BriefTest(unittest.TestCase):
    def test_saved_requires_the_problem_the_street_and_the_logging_words(self):
        data = voice.brief("saved", SAVED)
        self.assertIn("pothole", data["must_contain"])
        self.assertIn("Weston Lane", data["must_contain"])
        self.assertIn("logged", data["must_any"])
        self.assertEqual(data["limits"], {"max_chars": 300, "max_lines": 3})

    def test_a_photo_report_is_not_asked_for_a_photo(self):
        self.assertTrue(voice.brief("saved", SAVED)["ask"])
        self.assertFalse(voice.brief("saved", {**SAVED, "has_photo": True})["ask"])

    def test_duplicate_proves_it_is_one(self):
        data = voice.brief("duplicate", DUPLICATE)
        self.assertEqual(data["must_any"], ["already", "someone", "first"])

    def test_not_council_requires_the_organisation_and_its_number(self):
        data = voice.brief("not_council", NOT_COUNCIL)
        self.assertIn("National Highways", data["must_contain"])
        self.assertIn("0300 123 5000", data["must_contain"])
        self.assertIn("0300", data["allowed_numbers"])

    def test_no_answer_offers_to_help_rather_than_deflect(self):
        data = voice.brief("no_answer", NO_ANSWER)
        self.assertEqual(data["must_contain"], [])
        for phrase in ("tell me", "point you", "help with that"):
            self.assertIn(phrase, data["must_any"])

    def test_incomplete_asks_for_a_photo_unless_one_arrived(self):
        self.assertTrue(voice.brief("incomplete", INCOMPLETE)["ask"])
        self.assertFalse(voice.brief("incomplete", {**INCOMPLETE, "has_photo": True})["ask"])

    def test_emergency_requires_999_and_the_fixed_lead(self):
        data = voice.brief("emergency", {"contact": "999"})
        self.assertIn("999", data["must_contain"])
        self.assertIn("999", data["allowed_numbers"])
        self.assertIn(voice.EMERGENCY_LEAD, data["situation"])

    def test_the_link_never_reaches_the_model(self):
        data = voice.brief("saved", {**SAVED, "link": LINK})
        self.assertNotIn(LINK, json.dumps(data))
        self.assertNotIn("link", data)

    def test_an_unknown_kind_is_refused(self):
        with self.assertRaises(ValueError):
            voice.brief("shouting", SAVED)


class LintRuleTest(unittest.TestCase):
    def check(self, kind, facts, text, problem):
        problems = voice.lint(text, voice.brief(kind, facts))
        self.assertIn(problem, problems, f"{text!r} -> {problems}")
        return problems

    def test_a_good_reply_is_safe(self):
        for name, kind, facts, text in GOOD:
            with self.subTest(name):
                self.assertEqual(voice.lint(text, voice.brief(kind, facts)), [], text)

    def test_too_long(self):
        problems = voice.lint("logged pothole on Weston Lane. " + "x" * 300,
                              voice.brief("saved", SAVED))
        self.assertTrue(any(item.startswith("too_long") for item in problems), problems)

    def test_too_many_lines(self):
        self.check("saved", SAVED,
                   "logged pothole on Weston Lane.\none\ntwo\nthree", "too_many_lines:4")

    def test_urls(self):
        for address in ("https://example.com/x", "www.example.com", "google.com",
                        "example.com/search?q=pothole"):
            with self.subTest(address):
                self.check("saved", SAVED,
                           f"logged pothole on Weston Lane, look at {address}", "url")


    def test_the_deflection_phrases_are_banned(self):
        for phrase in ("honestly i'm not sure on that one",
                       "i don't know that one",
                       "i have no checked answer"):
            with self.subTest(phrase):
                problems = voice.lint("i can help with that - " + phrase,
                                      voice.brief("no_answer", {}))
                self.assertTrue(any(item.startswith("corporate:") for item in problems),
                                f"{phrase!r} -> {problems}")


    def test_a_missing_photo_ask_is_rejected(self):
        self.check("saved", SAVED,
                   "nice one, that's logged - pothole on Weston Lane.", "no_ask")

    def test_a_status_reply_cannot_claim_the_opposite(self):
        self.check("status", STATUS,
                   "quick update on the pothole at Weston Lane - it's being looked at by "
                   "the council and it's now closed.", "banned:closed")

    def test_a_bare_domain_is_a_url(self):
        self.check("saved", SAVED,
                   "logged pothole on Weston Lane. see southampton.gov.uk/x", "url")

    def test_a_crew_will_be_out_soon_is_a_promise(self):
        self.check("saved", SAVED,
                   "nice one, that's logged - pothole on Weston Lane. a crew will be out "
                   "soon.", "timescale:will_happen")

    def test_the_prompt_does_not_teach_a_banned_phrase(self):
        self.assertNotIn("honestly", voice.SYSTEM.lower())
        self.assertNotIn("no checked answer", voice.SYSTEM.lower())


    def test_an_unverified_policy_is_rejected(self):
        self.check("no_answer", NO_ANSWER,
                   "yes, you can put out two extra bags, where are you?", "banned:you can")

    def test_markdown(self):
        for mark in ("*logged*", "#logged", "`logged`", "logged_pothole"):
            with self.subTest(mark):
                self.check("saved", SAVED,
                           f"{mark} pothole on Weston Lane", "markdown")

    def test_em_dash(self):
        self.check("saved", SAVED, "logged \u2014 pothole on Weston Lane", "em_dash")

    def test_interested_in(self):
        self.check("saved", SAVED,
                   "logged pothole on Weston Lane, interested in updates?", "interested_in")

    def test_a_report_id_is_never_quoted(self):
        self.check("saved", SAVED, "logged pothole on Weston Lane, ref R-0042", "report_id")

    def test_corporate_phrases(self):
        for phrase in voice.CORPORATE:
            with self.subTest(phrase):
                self.check("saved", SAVED, f"logged pothole on Weston Lane, {phrase}.",
                           "corporate:" + phrase)

    def test_promised_timescales(self):
        samples = {
            "within": "logged pothole on Weston Lane, a crew will be out within 2 hours.",
            "counted": "logged pothole on Weston Lane, a crew will be out in 3 working days.",
            "finished": "logged pothole on Weston Lane, it will be fixed.",
            "guarantee": "logged pothole on Weston Lane, i can guarantee it.",
            "by_day": "logged pothole on Weston Lane, a crew will be out by tomorrow.",
        }
        for name, text in samples.items():
            with self.subTest(name):
                self.check("saved", SAVED, text, "timescale:" + name)

    def test_every_digit_must_come_from_the_facts(self):
        self.check("saved", SAVED,
                   "logged pothole on Weston Lane, that's 3 this month.", "number:3")

    def test_an_unconfirmed_team_is_never_named(self):
        self.check("saved", SAVED,
                   "logged pothole on Weston Lane, the Highways team are on it.",
                   "team:highways")

    def test_national_highways_is_a_real_organisation(self):
        problems = voice.lint(GOOD_BY_NAME["not_council"][2],
                              voice.brief("not_council", NOT_COUNCIL))
        self.assertNotIn("team:highways", problems)

    def test_a_missing_fact_is_caught(self):
        problems = self.check("saved", SAVED,
                              "nice one, that's logged. if you can grab a photo, send it over.",
                              "missing:pothole")
        self.assertIn("missing:Weston Lane", problems)

    def test_a_reply_that_proves_nothing_is_caught(self):
        self.check("saved", SAVED, "pothole on Weston Lane is sorted.", "no_meaning:"
                   + "|".join(voice.brief("saved", SAVED)["must_any"]))

    def test_incomplete_asks_exactly_one_question(self):
        self.check("incomplete", INCOMPLETE,
                   "pothole logged. where is it? which road?", "questions:2")
        self.check("incomplete", INCOMPLETE, "pothole logged. where is it", "questions:0")

    def test_case_and_a_leading_ah_are_tolerated(self):
        self.assertEqual(voice.lint("NICE ONE, THAT'S LOGGED - POTHOLE ON WESTON LANE. "
                                    "IF YOU CAN GRAB A PHOTO, SEND IT OVER.",
                                    voice.brief("saved", SAVED)), [])
        self.assertEqual(voice.lint("Ah, i can help with that - tell me a bit more.", voice.brief("no_answer", {})),
                         [])
        self.assertEqual(voice.lint(
            "Ah that one's not ours, sorry. National Highways handle motorways, "
            "ring them on 0300 123 5000.", voice.brief("not_council", NOT_COUNCIL)), [])

    def test_an_emergency_must_start_with_the_fixed_line(self):
        problems = voice.lint("999 now, tell them where it is.",
                             voice.brief("emergency", {"contact": "999"}))
        self.assertIn("emergency_lead", problems)

    def test_kind_specific_bans(self):
        self.check("saved", {**SAVED, "has_photo": True},
                   "logged pothole on Weston Lane, send a photo when you can.",
                   "banned:send a photo")
        self.check("photo_added", {"category_id": "pothole"},
                   "got your photo, thanks. send a photo if anything changes.",
                   "banned:send a photo")
        self.check("not_council", NOT_COUNCIL,
                   "not ours, we'll fix it anyway, ring 0300 123 5000.", "banned:we'll fix")

    def test_an_empty_reply_is_not_sendable(self):
        self.assertEqual(voice.lint("", voice.brief("saved", SAVED)), ["empty"])


class GenerateTest(unittest.TestCase):
    def test_reads_a_fenced_json_reply(self):
        chat = fake_chat(('```json\n{"text": "logged it"}\n```', "model"))
        with patch("voice.llm.chat", chat):
            self.assertEqual(voice.generate(voice.brief("saved", SAVED)), "logged it")

    def test_reads_json_wrapped_in_prose(self):
        chat = fake_chat(('Sure thing. {"text": "logged it"} ta', "model"))
        with patch("voice.llm.chat", chat):
            self.assertEqual(voice.generate(voice.brief("saved", SAVED)), "logged it")

    def test_hotter_and_with_a_full_budget(self):
        chat = fake_chat(spoken("logged it"))
        with patch("voice.llm.chat", chat):
            voice.generate(voice.brief("saved", SAVED))
        self.assertEqual(chat.calls[0]["temperature"], 0.9)
        self.assertEqual(chat.calls[0]["max_tokens"], 700)

    def test_no_model_means_no_text(self):
        chat = fake_chat(("stub words", "stub"))
        with patch("voice.llm.chat", chat):
            self.assertIsNone(voice.generate(voice.brief("saved", SAVED)))
        self.assertEqual(len(chat.calls), 1)

    def test_empty_text_is_no_text(self):
        chat = fake_chat(('{"text": "  "}', "model"))
        with patch("voice.llm.chat", chat):
            self.assertIsNone(voice.generate(voice.brief("saved", SAVED)))

    def test_one_retry_when_the_json_cannot_be_read(self):
        chat = fake_chat(("logged it, no json here", "model"), spoken("logged it"))
        with patch("voice.llm.chat", chat):
            self.assertEqual(voice.generate(voice.brief("saved", SAVED)), "logged it")
        self.assertEqual(len(chat.calls), 2)
        self.assertIn("JSON", chat.calls[1]["user"])

    def test_two_unreadable_replies_give_up(self):
        chat = fake_chat(("nope", "model"), ("still nope", "model"))
        with patch("voice.llm.chat", chat):
            self.assertIsNone(voice.generate(voice.brief("saved", SAVED)))
        self.assertEqual(len(chat.calls), 2)

    def test_the_system_prompt_carries_the_register(self):
        chat = fake_chat(spoken("logged it"))
        with patch("voice.llm.chat", chat):
            voice.generate(voice.brief("saved", SAVED))
        self.assertIn("British English", chat.calls[0]["system"])
        self.assertIn("must_contain", chat.calls[0]["system"])
        # The brief itself is the user turn, as JSON.
        self.assertEqual(json.loads(chat.calls[0]["user"])["kind"], "saved")


class SayTest(unittest.TestCase):
    def test_the_link_is_appended_exactly_once(self):
        chat = fake_chat(spoken(GOOD_BY_NAME["saved"][2]))
        with patch("voice.llm.chat", chat):
            reply = voice.say("saved", {**SAVED, "link": LINK}, BAD_TEMPLATE)
        self.assertTrue(reply.startswith(GOOD_BY_NAME["saved"][2]))
        self.assertEqual(reply.count(LINK), 1)
        self.assertEqual(reply.count("http"), 1)
        self.assertEqual(reply.splitlines()[-1], f"Follow it: {LINK}")

    def test_no_link_when_the_path_has_none(self):
        chat = fake_chat(spoken(GOOD_BY_NAME["greeting"][2]))
        with patch("voice.llm.chat", chat):
            reply = voice.say("greeting", {}, BAD_TEMPLATE)
        self.assertEqual(reply, GOOD_BY_NAME["greeting"][2])
        self.assertNotIn("Follow it", reply)

    def test_a_failed_lint_sends_the_template(self):
        out = io.StringIO()
        chat = fake_chat(spoken("logged pothole on Weston Lane, please be advised."))
        with patch("voice.llm.chat", chat), redirect_stdout(out):
            reply = voice.say("saved", {**SAVED, "link": LINK}, BAD_TEMPLATE)
        self.assertEqual(reply, BAD_TEMPLATE)
        self.assertIn("[voice] fallback saved", out.getvalue())
        self.assertIn("corporate", out.getvalue())

    def test_a_stub_model_sends_the_template(self):
        out = io.StringIO()
        chat = fake_chat(("stub words", "stub"))
        with patch("voice.llm.chat", chat), redirect_stdout(out):
            reply = voice.say("saved", {**SAVED, "link": LINK}, BAD_TEMPLATE)
        self.assertEqual(reply, BAD_TEMPLATE)
        self.assertIn("[voice] fallback saved no_text", out.getvalue())

    def test_a_broken_model_call_sends_the_template(self):
        out = io.StringIO()
        chat = fake_chat(RuntimeError("no route to host"))
        with patch("voice.llm.chat", chat), redirect_stdout(out):
            reply = voice.say("status", {**STATUS, "link": LINK}, BAD_TEMPLATE)
        self.assertEqual(reply, BAD_TEMPLATE)
        self.assertIn("[voice] fallback status", out.getvalue())

    def test_an_unknown_kind_sends_the_template(self):
        out = io.StringIO()
        with patch("voice.llm.chat", fake_chat(spoken("hi"))), redirect_stdout(out):
            self.assertEqual(voice.say("shouting", {}, BAD_TEMPLATE), BAD_TEMPLATE)
        self.assertIn("[voice] fallback shouting", out.getvalue())

    def test_a_model_url_is_never_sent(self):
        out = io.StringIO()
        chat = fake_chat(spoken("logged pothole on Weston Lane, see https://evil.example/r/x"))
        with patch("voice.llm.chat", chat), redirect_stdout(out):
            reply = voice.say("saved", {**SAVED, "link": LINK}, BAD_TEMPLATE)
        self.assertNotIn("evil.example", reply)
        self.assertEqual(reply.count(LINK), 1)
        self.assertEqual(reply, BAD_TEMPLATE)

    def test_an_emergency_keeps_its_first_line(self):
        chat = fake_chat(spoken(GOOD_BY_NAME["emergency"][2]))
        with patch("voice.llm.chat", chat):
            reply = voice.say("emergency", {"contact": "999"}, "Call 999 now.")
        self.assertTrue(reply.startswith("Call 999 now."))

    def test_two_runs_vary_the_words_and_keep_the_facts(self):
        first = "nice one, that's logged - pothole on Weston Lane. if you can grab a photo, send it over."
        second = "got it, pothole on Weston Lane is logged. if you can grab a photo, send it over."
        chat = fake_chat(spoken(first), spoken(second))
        with patch("voice.llm.chat", chat):
            one = voice.say("saved", {**SAVED, "link": LINK}, BAD_TEMPLATE)
            two = voice.say("saved", {**SAVED, "link": LINK}, BAD_TEMPLATE)
        self.assertNotEqual(one, two)
        for reply in (one, two):
            body = reply.split("\nFollow it:")[0]
            self.assertEqual(voice.lint(body, voice.brief("saved", SAVED)), [])
            self.assertIn("pothole", body)
            self.assertIn("Weston Lane", body)
            self.assertEqual(reply.count(LINK), 1)

    def test_nothing_sent_ever_carries_two_links(self):
        for name, kind, facts, text in GOOD:
            with self.subTest(name), patch("voice.llm.chat", fake_chat(spoken(text))):
                reply = voice.say(kind, {**facts, "link": LINK}, BAD_TEMPLATE)
                self.assertLessEqual(reply.count("http"), 1)
                self.assertEqual(reply.count(LINK), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)

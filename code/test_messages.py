"""Tests for every resident-facing string. No network, no database.

The copy rules in the plan are assertions here, not comments.

Run: python code/test_messages.py
"""

import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import messages  # noqa: E402

SAVED = {"link": "http://192.168.0.202:5005/r/token123", "duplicate_of": None}


def decision(**fields):
    base = {
        "category_id": "pothole",
        "category_label": "Pothole",
        "location": "Weston Lane",
        "has_photo": False,
        "severity": "high",
        "is_report": True,
        "reason": "ok",
    }
    base.update(fields)
    return base


def all_copy():
    """Every template, so the rules can be checked over the whole voice."""
    return {
        "logged": messages.logged(decision(), SAVED),
        "logged_photo": messages.logged(decision(has_photo=True), SAVED),
        "duplicate": messages.duplicate(decision(), SAVED),
        "need_location": messages.need_location(decision(location="")),
        "no_answer": messages.no_answer(decision(category_id="council_service_other")),
        "not_council_road": messages.not_council(
            decision(category_id="not_council_trunk_road",
                     category_label="Motorway or trunk road problem")),
        "not_council_utility": messages.not_council(
            decision(category_id="not_council_utility",
                     category_label="Utility problem")),
        "emergency": messages.emergency(),
        "unclear": messages.unclear(),
        "greeting": messages.greeting(),
        "status": messages.status({
            "category_id": "pothole",
            "location": "Weston Lane",
            "status_text": "being looked at by the council",
            "link": SAVED["link"],
        }),
    }


class CopyRuleTest(unittest.TestCase):
    def test_no_markdown(self):
        for name, text in all_copy().items():
            for character in ("*", "_", "#", "`", "**"):
                self.assertNotIn(character, text, name)

    def test_no_em_dash_and_no_banned_phrase(self):
        for name, text in all_copy().items():
            self.assertNotIn("\u2014", text, name)
            self.assertNotIn("interested in", text.lower(), name)

    def test_three_lines_at_most(self):
        for name, text in all_copy().items():
            lines = [line for line in text.splitlines() if line.strip()]
            self.assertLessEqual(len(lines), 3, f"{name}: {text!r}")

    def test_one_link_at_most(self):
        for name, text in all_copy().items():
            self.assertLessEqual(len(re.findall(r"https?://", text)), 1, name)

    def test_short_enough_for_a_text_message(self):
        for name, text in all_copy().items():
            self.assertLessEqual(len(text), 320, f"{name} is {len(text)} chars")

    def test_no_unconfirmed_team_is_named(self):
        book = json.loads((Path(messages.AGENT_DIR) / "categories.json")
                          .read_text(encoding="utf-8"))
        teams = {c["team"] for c in book["categories"]
                 if c.get("team") and not c.get("team_confirmed")}
        self.assertTrue(teams)
        # Only the council-report messages could claim a team. "National Highways"
        # is a real organisation, so the refusal copy is checked by its own test.
        copy = all_copy()
        for name in ("logged", "logged_photo", "duplicate", "need_location", "status"):
            for team in teams:
                self.assertNotIn(team.lower(), copy[name].lower(), f"{name} names {team}")

    def test_no_search_engine_links(self):
        for name, text in all_copy().items():
            self.assertNotIn("google.com", text.lower(), name)
            self.assertNotIn("search?q=", text.lower(), name)


class PathTest(unittest.TestCase):
    def test_logged_says_what_where_and_how_to_follow(self):
        text = messages.logged(decision(), SAVED)
        self.assertTrue(text.startswith("Logged: pothole, Weston Lane."))
        self.assertIn("Follow it:", text)
        self.assertIn(SAVED["link"], text)

    def test_a_photo_is_acknowledged(self):
        self.assertIn("Photo attached.", messages.logged(decision(has_photo=True), SAVED))

    def test_a_duplicate_is_linked_not_relogged(self):
        text = messages.duplicate(decision(), {**SAVED, "duplicate_of": "R-0069"})
        self.assertTrue(text.startswith("Already logged:"))
        self.assertIn("linked", text)

    def test_the_location_question_comes_from_the_rulebook(self):
        text = messages.need_location(decision(category_id="fly_tipping", location=""))
        self.assertIn("Where exactly is it", text)
        self.assertNotIn("Which road", text)

    def test_only_one_question_is_asked(self):
        text = messages.need_location(decision(location=""))
        self.assertEqual(text.count("?"), 1)

    def test_an_unanswered_question_points_at_an_official_page(self):
        text = messages.no_answer(decision(category_id="council_service_other"))
        self.assertIn("I do not have a checked answer", text)
        self.assertIn("southampton.gov.uk", text)

    def test_a_motorway_problem_names_national_highways_and_its_number(self):
        text = messages.not_council(decision(category_id="not_council_trunk_road"))
        self.assertIn("National Highways", text)
        self.assertIn("0300 123 5000", text)

    def test_a_utility_problem_does_not_pretend_the_council_handles_it(self):
        text = messages.not_council(decision(category_id="not_council_utility"))
        self.assertIn("not", text.lower())
        self.assertTrue("gov.uk" in text or "call" in text.lower())

    def test_an_emergency_starts_with_999(self):
        self.assertTrue(messages.emergency().startswith("Call 999 now."))

    def test_unclear_gives_an_example(self):
        self.assertIn("pothole outside 12 Alma Road", messages.unclear())

    def test_a_greeting_offers_examples(self):
        text = messages.greeting()
        self.assertIn("Pothole", text)
        self.assertIn("missed bin", text)

    def test_thanks_is_silence(self):
        self.assertEqual(messages.thanks(), "")

    def test_status_names_the_report_the_status_and_the_link(self):
        text = messages.status({
            "category_id": "pothole",
            "location": "Weston Lane",
            "status_text": "being looked at by the council",
            "link": SAVED["link"],
        })
        self.assertIn("pothole", text.lower())
        self.assertIn("Weston Lane", text)
        self.assertIn("being looked at by the council", text)
        self.assertIn(SAVED["link"], text)

    def test_labels_read_naturally(self):
        text = messages.logged(
            decision(category_id="litter_street_cleaning",
                     category_label="Litter / street needs cleaning"), SAVED)
        self.assertTrue(text.startswith("Logged: litter / street needs cleaning,"))


if __name__ == "__main__":
    unittest.main(verbosity=2)

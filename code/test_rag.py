"""Tests for fact-grounded answers. No network.

Run: python code/test_rag.py
"""

import unittest
import unittest.mock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import rag  # noqa: E402


def model_reply(answer="Repairs depend on depth.", facts=(1,)):
    return (rag.json.dumps({"answer": answer, "facts": list(facts)}), "model")


class CorpusTest(unittest.TestCase):
    def test_every_fact_has_a_source_and_a_date(self):
        facts = rag.corpus()
        self.assertGreaterEqual(len(facts), 50)
        for fact in facts:
            self.assertTrue(fact["date_checked"], fact["topic"])
            self.assertTrue(fact["source_name"], fact["topic"])
            if fact["kind"] == "fact":
                self.assertTrue(fact["url"], fact["topic"])

    def test_a_contact_without_a_page_is_allowed(self):
        emergency = next(f for f in rag.corpus() if f["topic"] == "Emergency services")
        self.assertEqual(emergency["kind"], "contact")
        self.assertIn("999", emergency["text"])

    def test_the_contacts_are_in_the_corpus(self):
        topics = [fact["topic"].lower() for fact in rag.corpus()]
        self.assertTrue(any("national highways" in topic for topic in topics))

    def test_the_facts_are_numbered_in_the_prompt(self):
        block = rag._number(rag.corpus()[:2])
        self.assertIn("[1]", block)
        self.assertIn("[2]", block)


class PickTest(unittest.TestCase):
    def test_valid_indices_survive(self):
        self.assertEqual(rag._pick([1, "2", 2, 3], 10), [1, 2, 3])

    def test_out_of_range_is_dropped(self):
        self.assertEqual(rag._pick([0, 99, -1], 10), [])

    def test_junk_is_dropped(self):
        self.assertEqual(rag._pick(["pothole", None, 1.7], 10), [1])

    def test_at_most_three_are_cited(self):
        self.assertEqual(len(rag._pick([1, 2, 3, 4, 5], 10)), rag.MAX_CITED)


class JsonTest(unittest.TestCase):
    def test_plain_json(self):
        self.assertEqual(rag._json_object('{"answer": "x", "facts": [1]}')["answer"], "x")

    def test_fenced_json(self):
        raw = '```json\n{"answer": "x", "facts": [1]}\n```'
        self.assertEqual(rag._json_object(raw)["facts"], [1])

    def test_prose_around_json(self):
        raw = 'Here: {"answer": "x", "facts": [2]} done'
        self.assertEqual(rag._json_object(raw)["facts"], [2])

    def test_garbage_is_none(self):
        self.assertIsNone(rag._json_object("I cannot help with that"))


class SourceLineTest(unittest.TestCase):
    def test_one_fact(self):
        fact = {"source_name": "Reporting environmental issues",
                "date_checked": "2026-10-17", "url": "https://southampton.gov.uk/x"}
        line = rag.source_line([fact])
        self.assertIn("Reporting environmental issues", line)
        self.assertIn("2026-10-17", line)
        self.assertIn("https://southampton.gov.uk/x", line)

    def test_several_facts_are_named_but_only_one_link_is_given(self):
        line = rag.source_line([
            {"source_name": "A", "date_checked": "2026-10-17", "url": "https://a"},
            {"source_name": "B", "date_checked": "2026-10-17", "url": "https://b"},
            {"source_name": "C", "date_checked": "2026-10-17", "url": "https://c"},
        ])
        self.assertIn("A", line)
        self.assertIn("C", line)
        self.assertEqual(line.count("https://"), 1)

    def test_no_facts_is_an_empty_line(self):
        self.assertEqual(rag.source_line([]), "")


class AnswerTest(unittest.TestCase):
    def test_a_reply_cites_the_facts_the_model_picked(self):
        with unittest.mock.patch.object(rag.llm, "chat", return_value=model_reply(facts=(17,))):
            text, used = rag.answer("how long does a pothole take to fix")
        self.assertIn("Repairs depend on depth.", text)
        self.assertIn("Source:", text)
        self.assertEqual(used[0]["topic"], rag.corpus()[16]["topic"])
        self.assertIn(used[0]["url"], text)

    def test_a_model_written_url_is_removed(self):
        with unittest.mock.patch.object(
            rag.llm, "chat",
            return_value=model_reply(answer="See https://made-up.example/x now.", facts=(1,)),
        ):
            text, _ = rag.answer("how long does a pothole take to fix")
        self.assertNotIn("made-up.example", text)
        self.assertIn("Source:", text)

    def test_empty_facts_means_no_answer(self):
        with unittest.mock.patch.object(rag.llm, "chat", return_value=model_reply(facts=())):
            text, used = rag.answer("what is the meaning of life")
        self.assertEqual(text, "")
        self.assertEqual(used, [])

    def test_an_invalid_index_means_no_answer(self):
        with unittest.mock.patch.object(rag.llm, "chat", return_value=model_reply(facts=(999,))):
            text, _ = rag.answer("anything")
        self.assertEqual(text, "")

    def test_a_stub_reply_is_not_an_answer(self):
        with unittest.mock.patch.object(rag.llm, "chat", return_value=("stub", "stub")):
            text, used = rag.answer("how long does a pothole take to fix")
        self.assertEqual(text, "")
        self.assertEqual(used, [])

    def test_one_bad_reply_is_retried_once(self):
        replies = [("not json", "model"), model_reply(facts=(1,))]
        with unittest.mock.patch.object(rag.llm, "chat", side_effect=replies) as chat:
            text, _ = rag.answer("how long does a pothole take to fix")
        self.assertIn("Source:", text)
        self.assertEqual(chat.call_count, 2)

    def test_two_bad_replies_give_up(self):
        with unittest.mock.patch.object(rag.llm, "chat", return_value=("nope", "model")):
            text, _ = rag.answer("how long does a pothole take to fix")
        self.assertEqual(text, "")

    def test_the_model_is_told_to_use_only_the_facts(self):
        with unittest.mock.patch.object(rag.llm, "chat", return_value=model_reply()) as chat:
            rag.answer("how long does a pothole take to fix")
        system = chat.call_args[0][0]
        self.assertIn("Use only those facts", system)
        self.assertIn("empty facts list", system)
        self.assertIn("[1]", system)

    def test_the_triage_category_is_passed_as_a_hint(self):
        with unittest.mock.patch.object(rag.llm, "chat", return_value=model_reply()) as chat:
            rag.answer("how long does it take", category_id="pothole")
        self.assertIn("triaged as: pothole", chat.call_args[0][0])


if __name__ == "__main__":
    unittest.main(verbosity=2)

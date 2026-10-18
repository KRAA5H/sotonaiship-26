"""Tests for the graph shell. Offline, MemorySaver, temporary thread store.

Run: python code/test_graph_runtime.py
"""

import contextlib
import io
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from langgraph.checkpoint.memory import MemorySaver  # noqa: E402
from langgraph.checkpoint.sqlite import SqliteSaver  # noqa: E402

import reports_db  # noqa: E402
from graph import runtime as graph_runtime  # noqa: E402
from graph import store  # noqa: E402

FIXED = datetime(2026, 10, 18, 4, 0, tzinfo=timezone.utc)


class RuntimeCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "kerbside.db"
        store.migrate(self.db)
        self.threads = store.ThreadStore(self.db)
        self.runtime = self.make_runtime()

    def make_runtime(self, checkpointer=None):
        deps = graph_runtime.Deps(threads=self.threads, playbooks={},
                                  now=lambda: FIXED)
        return graph_runtime.TurnRuntime(deps, checkpointer or MemorySaver())

    def turn(self, text, guid, sender="+447700900001", photo_ref=None):
        inbound = {"sender": sender, "text": text, "message_guid": guid}
        if photo_ref:
            inbound["photo_ref"] = photo_ref
        return self.runtime.turn(inbound)

    def count_reports(self):
        conn = reports_db.connect(self.db)
        try:
            return conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
        finally:
            conn.close()


class HydrateTest(RuntimeCase):
    def test_a_new_thread_is_created_with_one_message(self):
        result = self.turn("there is a tree fallen on the road", "g-1")
        state = result["state"]
        self.assertEqual(result["kind"], "captured")
        self.assertTrue(result["thread_id"].startswith("h-"))
        self.assertEqual(state["turn_id"], "g-1")
        self.assertEqual(len(state["recent_messages"]), 1)
        self.assertIn("tree", state["incident_draft"]["description"])
        self.assertEqual(state["incident_draft"]["capture_state"], "captured")
        self.assertEqual(state["incident_draft"]["routing_status"], "needs_review")
        self.assertIsNone(state["incident_draft"]["category_id"])

    def test_a_second_turn_reuses_the_thread_and_appends(self):
        first = self.turn("there is a tree fallen on the road", "g-1")
        result = self.turn("it is near the school", "g-2")
        self.assertEqual(result["thread_id"], first["thread_id"])
        self.assertEqual(len(result["state"]["recent_messages"]), 2)
        row = self.threads.load(result["thread_id"])
        self.assertEqual(row["last_turn_id"], "g-2")
        self.assertEqual(row["turn_version"], 2)
        self.assertEqual(row["incident_draft"]["capture_state"], "captured")

    def test_a_repeated_turn_is_suppressed_without_a_second_message(self):
        first = self.turn("there is a tree fallen on the road", "g-1")
        second = self.turn("there is a tree fallen on the road", "g-1")
        self.assertEqual(second["kind"], "duplicate")
        self.assertTrue(second["state"]["suppressed"])
        self.assertEqual(len(second["state"]["recent_messages"]), 1)
        self.assertEqual(second["thread_id"], first["thread_id"])


class PrecheckTest(RuntimeCase):
    def test_empty_input_is_suppressed(self):
        result = self.turn("", "g-empty")
        self.assertEqual(result["kind"], "suppressed")
        self.assertTrue(result["state"]["suppressed"])

    def test_an_emergency_stops_before_capture(self):
        result = self.turn("there is a gas leak in the kitchen", "g-emergency")
        self.assertEqual(result["kind"], "emergency")
        self.assertTrue(result["state"]["emergency"])
        self.assertTrue(result["state"]["short_circuit"])
        self.assertNotIn("tree", (result["state"]["incident_draft"] or {}).get("description", ""))

    def test_a_threat_is_not_an_emergency(self):
        result = self.turn("I will hurt you", "g-threat")
        self.assertEqual(result["kind"], "short_circuit")
        self.assertFalse(result["state"]["emergency"])
        self.assertTrue(result["state"]["short_circuit"])

    def test_a_greeting_takes_the_cheap_edge(self):
        result = self.turn("hello", "g-hello")
        self.assertEqual(result["kind"], "greeting")
        self.assertTrue(result["state"]["short_circuit"])

    def test_a_thank_you_is_silence(self):
        result = self.turn("thanks", "g-thanks")
        self.assertEqual(result["kind"], "suppressed")
        self.assertTrue(result["state"]["suppressed"])


class CaptureTest(RuntimeCase):
    def test_capture_does_not_write_a_report_row(self):
        self.turn("there is a tree fallen on the road", "g-1")
        self.assertEqual(self.count_reports(), 0)

    def test_a_photo_only_message_captures_a_reference(self):
        result = self.turn("", "g-photo", photo_ref="guid:1")
        draft = result["state"]["incident_draft"]
        self.assertEqual(result["kind"], "captured")
        self.assertEqual(draft["description"], "")
        self.assertEqual(draft["attachments"], [{"kind": "photo", "ref": "guid:1"}])

    def test_the_playbook_index_is_available_to_the_runtime(self):
        index = graph_runtime.load_playbooks()
        self.assertEqual(index["generated_from"]["category_count"], 22)
        self.assertIn("unclear_other", index["categories"])


class CheckpointerTest(RuntimeCase):
    def test_sqlite_saver_resumes_the_thread(self):
        with SqliteSaver.from_conn_string(str(self.db)) as saver:
            runtime = self.make_runtime(saver)
            runtime.turn({"sender": "+447700900009", "text": "one", "message_guid": "g-1"})
        with SqliteSaver.from_conn_string(str(self.db)) as saver:
            runtime = self.make_runtime(saver)
            result = runtime.turn({"sender": "+447700900009", "text": "two",
                                   "message_guid": "g-2"})
        self.assertEqual(len(result["state"]["recent_messages"]), 2)


class CliTest(RuntimeCase):
    def test_selftest_and_a_turn(self):
        self.assertEqual(len(graph_runtime.selftest()), 6)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = graph_runtime.main(["--turn", "there is a tree fallen on the road",
                                       "--db", str(self.db)])
        self.assertEqual(code, 0)
        self.assertIn("captured", out.getvalue())
        self.assertIn("tree", out.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)

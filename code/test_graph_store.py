"""Tests for graph storage. Temp database per test, no network, no model.

Run: python code/test_graph_store.py
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import reports_db  # noqa: E402
from graph import store  # noqa: E402
from graph.state import new_incident_draft  # noqa: E402


class StoreCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "kerbside.db"
        store.migrate(self.db)

    def query(self, sql, args=()):
        conn = reports_db.connect(self.db)
        try:
            return conn.execute(sql, args).fetchall()
        finally:
            conn.close()


class MigrationTest(StoreCase):
    def test_tables_exist(self):
        names = {row["name"] for row in self.query(
            "SELECT name FROM sqlite_master WHERE type = 'table'")}
        for name in ("reports", "threads", "turn_operations", "delivery_outbox", "claims_sent"):
            self.assertIn(name, names)

    def test_migrate_is_idempotent(self):
        store.migrate(self.db)
        store.migrate(self.db)
        columns = [row["name"] for row in self.query("PRAGMA table_info(reports)")]
        self.assertEqual(len(columns), len(set(columns)))

    def test_capture_and_routing_columns_have_defaults(self):
        columns = {row["name"] for row in self.query("PRAGMA table_info(reports)")}
        self.assertIn("capture_state", columns)
        self.assertIn("routing_status", columns)
        conn = reports_db.connect(self.db)
        try:
            conn.execute(
                "INSERT INTO reports (id, created_at, category_id, status, link_token) "
                "VALUES ('R-0001', '2026-10-18T00:00:00+00:00', 'pothole', 'new', 'tok1234567890')")
        finally:
            conn.close()
        row = self.query("SELECT capture_state, routing_status FROM reports WHERE id = 'R-0001'")[0]
        self.assertEqual(row["capture_state"], "captured")
        self.assertEqual(row["routing_status"], "needs_review")

    def test_reports_columns_include_the_policy_fields(self):
        self.assertIn("capture_state", reports_db.COLUMNS)
        self.assertIn("routing_status", reports_db.COLUMNS)


class ThreadStoreTest(StoreCase):
    def test_missing_thread_returns_none(self):
        self.assertIsNone(store.ThreadStore(self.db).load("h-missing"))

    def test_round_trip_survives_a_new_instance(self):
        threads = store.ThreadStore(self.db)
        draft = new_incident_draft("tree down", {"text": "Not given"})
        saved = threads.save(
            "h-1", active_incident_id="R-0001",
            pending_question={"field": "location", "text": "where is it",
                              "asked_at": "2026-10-18T00:00:00+00:00", "turn_id": "g-1"},
            last_action="ask", last_claims=["i've saved that here"],
            last_turn_id="g-1", incident_draft=draft)
        self.assertEqual(saved["turn_version"], 1)
        loaded = store.ThreadStore(self.db).load("h-1")
        self.assertEqual(loaded["pending_question"]["field"], "location")
        self.assertEqual(loaded["last_claims"], ["i've saved that here"])
        self.assertEqual(loaded["incident_draft"]["description"], "tree down")
        self.assertEqual(loaded["incident_draft"]["version"], 0)

    def test_version_increments_and_omitted_fields_stay(self):
        threads = store.ThreadStore(self.db)
        threads.save("h-1", last_action="ask", last_claims=["one"])
        second = threads.save("h-1", last_action="log")
        self.assertEqual(second["turn_version"], 2)
        self.assertEqual(second["last_claims"], ["one"])

    def test_explicit_none_clears_a_field(self):
        threads = store.ThreadStore(self.db)
        threads.save("h-1", pending_question={"field": "location", "text": "where"})
        cleared = threads.save("h-1", pending_question=None)
        self.assertIsNone(cleared["pending_question"])


class OutboxTest(StoreCase):
    def test_order_and_unique_operation_key(self):
        outbox = store.Outbox(self.db)
        self.assertIsNotNone(outbox.enqueue("h-1", 2, "link", "g-1:2"))
        self.assertIsNotNone(outbox.enqueue("h-1", 1, "words", "g-1:1"))
        self.assertIsNone(outbox.enqueue("h-1", 1, "words", "g-1:1"))
        self.assertEqual([row["body"] for row in outbox.pending()], ["words", "link"])

    def test_mark_moves_state_and_stamps_sent(self):
        outbox = store.Outbox(self.db)
        row_id = outbox.enqueue("h-1", 1, "words", "g-1:1")
        self.assertTrue(outbox.mark(row_id, "sent"))
        self.assertFalse(outbox.mark(9999, "sent"))
        self.assertFalse(outbox.mark(row_id, "teleported"))
        row = self.query("SELECT state, sent_at FROM delivery_outbox WHERE id = ?", (row_id,))[0]
        self.assertEqual(row["state"], "sent")
        self.assertIsNotNone(row["sent_at"])
        self.assertEqual(outbox.pending(), [])

    def test_fail_orphans_marks_only_queued(self):
        outbox = store.Outbox(self.db)
        first = outbox.enqueue("h-1", 1, "one", "g-1:1")
        outbox.enqueue("h-1", 2, "two", "g-1:2")
        outbox.mark(first, "sent")
        self.assertEqual(outbox.fail_orphans(), 1)
        self.assertEqual([row["state"] for row in self.query(
            "SELECT state FROM delivery_outbox ORDER BY seq")], ["sent", "undeliverable"])

    def test_error_is_kept(self):
        outbox = store.Outbox(self.db)
        row_id = outbox.enqueue("h-1", 1, "words", "g-1:1")
        outbox.mark(row_id, "ambiguous", "timeout")
        row = self.query("SELECT state, error FROM delivery_outbox WHERE id = ?", (row_id,))[0]
        self.assertEqual((row["state"], row["error"]), ("ambiguous", "timeout"))


class TurnOperationsTest(StoreCase):
    def test_record_once_and_read_back(self):
        ops = store.TurnOperations(self.db)
        self.assertIsNone(ops.get("g-1", "commit"))
        self.assertTrue(ops.record("g-1", "commit", {"report_id": "R-0001"}))
        self.assertEqual(ops.get("g-1", "commit")["report_id"], "R-0001")
        self.assertFalse(ops.record("g-1", "commit", {"report_id": "R-0002"}))
        self.assertEqual(ops.get("g-1", "commit")["report_id"], "R-0001")
        self.assertEqual(len(self.query("SELECT 1 FROM turn_operations")), 1)


class ClaimsTest(StoreCase):
    def test_recent_is_newest_first(self):
        claims = store.Claims(self.db)
        for bubble in ("first", "second", "third"):
            claims.record("h-1", "g-1", bubble)
        self.assertEqual(claims.recent("h-1", limit=2), ["third", "second"])


class PrivacyTest(StoreCase):
    def test_no_contact_or_coordinate_column(self):
        for table in ("threads", "delivery_outbox", "claims_sent"):
            columns = {row["name"] for row in self.query(f"PRAGMA table_info({table})")}
            for forbidden in ("chat_guid", "phone", "phone_number", "name", "lat", "lng"):
                with self.subTest(table=table, forbidden=forbidden):
                    self.assertNotIn(forbidden, columns)


if __name__ == "__main__":
    unittest.main(verbosity=2)

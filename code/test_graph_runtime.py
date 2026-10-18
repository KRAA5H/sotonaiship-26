"""Tests for the graph shell. Offline, MemorySaver, temporary thread store.

Run: python code/test_graph_runtime.py
"""

import contextlib
import io
import json
import sys
import tempfile
import unittest
import unittest.mock
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

    def make_runtime(self, checkpointer=None, llm=None):
        deps = graph_runtime.Deps(threads=self.threads, playbooks=graph_runtime.load_playbooks(), llm=llm,
                                  reports=self.db, now=lambda: FIXED,
                                  ops=store.TurnOperations(self.db),
                                  outbox=store.Outbox(self.db),
                                  claims=store.Claims(self.db))
        return graph_runtime.TurnRuntime(deps, checkpointer or MemorySaver())

    def turn(self, text, guid, sender="+447700900001", photo_ref=None, image_ref=None,
             card=None):
        inbound = {"sender": sender, "text": text, "message_guid": guid}
        if photo_ref:
            inbound["photo_ref"] = photo_ref
        if image_ref:
            inbound["image_ref"] = image_ref
        if card:
            inbound["card"] = card
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
        self.assertEqual(result["kind"], "saved")
        self.assertTrue(result["thread_id"].startswith("h-"))
        self.assertEqual(state["turn_id"], "g-1")
        self.assertEqual(len(state["recent_messages"]), 1)
        self.assertIn("tree", state["incident_draft"]["description"])
        self.assertEqual(state["incident_draft"]["capture_state"], "captured")
        self.assertEqual(state["incident_draft"]["routing_status"], "needs_review")
        self.assertEqual(state["incident_draft"]["category_id"], "unclear_other")

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
        self.assertEqual(second["state"]["suppressed"], True)
        self.assertEqual(len(second["state"]["recent_messages"]), 1)
        self.assertEqual(second["thread_id"], first["thread_id"])

    def test_a_duplicate_does_not_wipe_the_thread_memory(self):
        first = self.turn("there is a tree fallen on the road", "g-1")
        thread_id = first["thread_id"]
        draft = self.threads.load(thread_id)["incident_draft"]
        pending = {"field": "street", "text": "where is it?",
                   "asked_at": "2026-10-18T04:00:00", "turn_id": "g-1"}
        self.threads.save(thread_id, last_turn_id="g-1", incident_draft=draft,
                          pending_question=pending, last_claims=["saved here"])
        self.turn("there is a tree fallen on the road", "g-1")
        row = self.threads.load(thread_id)
        self.assertEqual(row["incident_draft"], draft)
        self.assertEqual(row["pending_question"]["field"], "street")
        self.assertEqual(row["last_claims"], ["saved here"])


class PrecheckTest(RuntimeCase):
    def test_empty_input_is_suppressed(self):
        result = self.turn("", "g-empty")
        self.assertEqual(result["kind"], "empty")
        self.assertTrue(result["state"]["suppressed"])

    def test_an_emergency_stops_before_capture(self):
        result = self.turn("there is a gas leak in the kitchen", "g-emergency")
        self.assertEqual(result["kind"], "emergency")
        self.assertTrue(result["state"]["emergency"])
        self.assertTrue(result["state"]["short_circuit"])
        self.assertNotIn("tree", (result["state"]["incident_draft"] or {}).get("description", ""))

    def test_a_threat_is_not_an_emergency(self):
        result = self.turn("I will hurt you", "g-threat")
        self.assertEqual(result["kind"], "threat")
        self.assertFalse(result["state"]["emergency"])
        self.assertTrue(result["state"]["short_circuit"])

    def test_a_fire_station_is_not_an_emergency(self):
        result = self.turn("pothole outside the fire station on Winchester Road", "g-fire-station")
        self.assertEqual(result["kind"], "saved")
        self.assertFalse(result["state"]["emergency"])

    def test_a_house_fire_is_an_emergency(self):
        result = self.turn("the house is on fire", "g-house-fire")
        self.assertEqual(result["kind"], "emergency")
        self.assertTrue(result["state"]["emergency"])

    def test_a_greeting_takes_the_cheap_edge(self):
        result = self.turn("hello", "g-hello")
        self.assertEqual(result["kind"], "greeting")
        self.assertTrue(result["state"]["short_circuit"])

    def test_a_thank_you_is_silence(self):
        result = self.turn("thanks", "g-thanks")
        self.assertEqual(result["kind"], "silence")
        self.assertTrue(result["state"]["suppressed"])


class FakeLLM:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    def chat(self, system, user, **kwargs):
        self.calls += 1
        reply = self.replies.pop(0) if self.replies else "{}"
        if isinstance(reply, tuple):
            return reply
        return reply, "model"


def model_plan(**changes):
    base = {
        "dialogue_act": "new_report", "action": "log",
        "incident_patch": {}, "service_candidates": ["unclear_other"],
        "specialist_request": None, "clarification": None,
        "fact_request": None, "escalation": None,
        "retracted_claims": [], "reason_codes": [],
    }
    base.update(changes)
    return json.dumps(base)


class DecideTest(RuntimeCase):
    def use(self, replies):
        fake = FakeLLM(replies)
        self.runtime = self.make_runtime(llm=fake)
        return fake

    def test_a_wrong_info_only_plan_is_repaired_to_unclear_other(self):
        fake = self.use([model_plan(
            service_candidates=["flooding_severe_weather"],
            incident_patch={"set": {"category_id": "flooding_severe_weather"}})])
        result = self.turn("there is a tree fallen on the road", "g-1")
        self.assertEqual(result["kind"], "saved")
        self.assertEqual(result["state"]["repair_count"], 1)
        self.assertEqual(fake.calls, 1)
        row = self.row()
        self.assertEqual(row["category_id"], "unclear_other")
        self.assertIn("hasn't gone to the council", " ".join(result["bubbles"]))

    def test_a_model_ask_for_location_still_saves_first(self):
        self.use([model_plan(
            action="ask", service_candidates=["unclear_other"],
            clarification={"field": "location", "reason": "Where is it?"},
            incident_patch={"set": {"category_id": "unclear_other"}})])
        result = self.turn("there is a tree fallen on the road", "g-1")
        self.assertEqual(result["kind"], "saved")
        self.assertEqual(self.count_reports(), 1)
        self.assertEqual(result["state"]["pending_question"]["field"], "location")
        self.assertEqual(" ".join(result["bubbles"]).count("?"), 1)

    def test_an_invalid_model_reply_falls_back_to_capture(self):
        fake = self.use([("this is not json", "model")])
        result = self.turn("there is a tree fallen on the road", "g-1")
        self.assertEqual(result["kind"], "saved")
        self.assertIn("plan_invalid", result["state"]["degraded"])
        self.assertEqual(fake.calls, 1)
        self.assertEqual(self.count_reports(), 1)

    def test_a_not_council_plan_is_not_saved(self):
        self.use([model_plan(
            service_candidates=["not_council_utility"],
            incident_patch={"set": {"category_id": "not_council_utility"}})])
        result = self.turn("there is a power cut on Alma Road", "g-1")
        self.assertEqual(result["kind"], "escalated")
        self.assertEqual(self.count_reports(), 0)
        self.assertIn("not southampton city council", " ".join(result["bubbles"]).lower())

    def test_an_answer_uses_a_checked_fact(self):
        self.use([model_plan(
            dialogue_act="question", action="answer", service_candidates=["missed_bin"],
            fact_request={"question": "what do I do about a missed bin?",
                          "category_id": "missed_bin"})])
        result = self.turn("what do I do about a missed bin?", "g-1")
        self.assertEqual(result["kind"], "answered")
        self.assertEqual(self.count_reports(), 0)
        facts = result["state"]["executed_outcome"]["facts"]
        self.assertTrue(facts)
        self.assertTrue(facts[0]["url"].startswith("https://"))
        self.assertEqual(facts[0]["date"], "2026-10-17")

    def test_an_a33_pothole_is_pointed_to_national_highways_not_saved(self):
        result = self.turn("pothole on the A33", "g-1")
        self.assertEqual(result["kind"], "escalated")
        self.assertEqual(self.count_reports(), 0)
        joined = " ".join(result["bubbles"]).lower()
        self.assertIn("national highways", joined)
        self.assertIn("0300 123 5000", joined)
        self.assertNotIn("hasn't gone to the council", joined)

    def test_a_winchester_pothole_is_not_saved(self):
        result = self.turn("pothole in Winchester", "g-1")
        self.assertEqual(result["kind"], "escalated")
        self.assertEqual(self.count_reports(), 0)
        self.assertIn("not southampton city council", " ".join(result["bubbles"]).lower())

    def test_a_noise_complaint_goes_to_the_council_form(self):
        result = self.turn("loud music every night from next door", "g-1")
        self.assertEqual(result["kind"], "escalated")
        self.assertEqual(self.count_reports(), 0)
        self.assertIn("form", " ".join(result["bubbles"]).lower())
        self.assertIn("envir", (result.get("source_url") or "").lower())

    def test_a_status_question_answers_the_open_report(self):
        self.turn("pothole on Alma Road", "g-1")
        result = self.turn("any update on my report?", "g-2")
        self.assertEqual(result["kind"], "answered")
        self.assertEqual(self.count_reports(), 1)
        joined = " ".join(result["bubbles"])
        self.assertIn("Update on your pothole", joined)
        self.assertIn("Alma Road", joined)
        self.assertTrue(result["url"].startswith("http"))

    def test_a_card_only_message_updates_the_open_report(self):
        first = self.turn("pothole on Alma Road", "g-1")
        self.assertEqual(first["kind"], "saved")
        with unittest.mock.patch(
                "agents.location_agent.LocationAgent.shared_place",
                return_value={"street_name": "Weston Lane", "area": "Bevois",
                              "postcode": None, "in_city": True}):
            result = self.turn("", "g-2", card="BEGIN:VCARD X-APPLE-STRUCTURED-LOCATION:geo:50.9,-1.4 END:VCARD")
        self.assertEqual(result["kind"], "saved")
        self.assertEqual(self.count_reports(), 1)
        self.assertEqual(self.row()["location"], "Weston Lane")

    def test_an_emergency_never_calls_the_model(self):
        fake = self.use([model_plan()])
        result = self.turn("there is a gas leak in the kitchen", "g-1")
        self.assertEqual(result["kind"], "emergency")
        self.assertEqual(fake.calls, 0)
        self.assertEqual(self.count_reports(), 0)

    def row(self):
        conn = reports_db.connect(self.db)
        try:
            return conn.execute("SELECT * FROM reports").fetchone()
        finally:
            conn.close()


class CaptureTest(RuntimeCase):
    def test_a_tree_writes_one_unclear_other_row(self):
        result = self.turn("there is a tree fallen on the road", "g-1")
        self.assertEqual(self.count_reports(), 1)
        conn = reports_db.connect(self.db)
        try:
            row = conn.execute("SELECT category_id, location, capture_state, routing_status "
                               "FROM reports").fetchone()
        finally:
            conn.close()
        self.assertEqual(row["category_id"], "unclear_other")
        self.assertEqual(row["location"], "Not given")
        self.assertEqual(row["capture_state"], "captured")
        self.assertEqual(row["routing_status"], "needs_review")
        self.assertIn("hasn't gone to the council", " ".join(result["bubbles"]))

    def test_a_photo_only_message_captures_a_reference(self):
        result = self.turn("", "g-photo", photo_ref="guid:1")
        draft = result["state"]["incident_draft"]
        self.assertEqual(result["kind"], "saved")
        self.assertEqual(draft["description"], "Photo of a problem")
        self.assertEqual(draft["attachments"], [{"kind": "photo", "ref": "guid:1"}])
        row = self.row()
        self.assertEqual(row["photo_guid"], "1")
        self.assertEqual(row["photo_mime"], "image/jpeg")

    def test_a_photo_tuple_is_stored_as_a_guid(self):
        result = self.turn("", "g-photo-t", photo_ref=("G-ABC", "image/jpeg"))
        draft = result["state"]["incident_draft"]
        self.assertEqual(result["kind"], "saved")
        self.assertEqual(draft["attachments"], [{"kind": "photo", "ref": "guid:G-ABC",
                                                  "features": {"mime": "image/jpeg"}}])

    def test_an_image_ref_is_a_photo(self):
        result = self.turn("", "g-image", image_ref="guid:2")
        draft = result["state"]["incident_draft"]
        self.assertEqual(result["kind"], "saved")
        self.assertEqual(draft["attachments"], [{"kind": "photo", "ref": "guid:2"}])

    def row(self):
        conn = reports_db.connect(self.db)
        try:
            return conn.execute("SELECT * FROM reports").fetchone()
        finally:
            conn.close()

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
        self.assertIn("saved", out.getvalue())
        self.assertIn("tree", out.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""Trajectory fixtures: the conversations the graph must get right.

Step 1 validates the fixture set and records which cases the legacy path already
fails. Graph and channel cases are loaded and skipped until those runtimes exist.

Run: python code/test_trajectories.py
"""

import json
import os
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import agents  # noqa: E402
import location  # noqa: E402
import reports_db  # noqa: E402
import tools  # noqa: E402
import triage  # noqa: E402
import voice  # noqa: E402
from agents import Turn, memory  # noqa: E402
from graph import store  # noqa: E402
from graph.runtime import Deps, TurnRuntime  # noqa: E402
from langgraph.checkpoint.memory import MemorySaver  # noqa: E402

CASES_FILE = Path(__file__).resolve().parent / "eval" / "trajectories" / "cases.json"
O = agents.ORCHESTRATOR

REQUIRED_CASE = {"name", "layer", "legacy", "turns", "expect"}
REQUIRED_EXPECT = {"rows", "categories", "locations", "reply_contains", "reply_forbids"}
KNOWN_CASE = REQUIRED_CASE | {"note", "specialist", "repeat_turn"}
KNOWN_EXPECT = REQUIRED_EXPECT | {"max_questions", "has_photo", "retracted",
                                  "draft_preserved", "reroutes", "patch_preserved",
                                  "replies", "pending_resumed"}
LAYERS = {"agent", "graph", "channel"}
LEGACY = {"pass", "fail", "not_applicable", "unverified"}
# Applied to every reply, not just the case's own forbidden list. A graph that
# claims council receipt or a crew must fail even when a fixture forgot to say so.
NEVER_SAID = ("The council has", "crew", "will be", "on its way")


def load_cases():
    return json.loads(CASES_FILE.read_text(encoding="utf-8"))


class FakeGeocoder:
    place = {"street_name": "Weston Lane", "postcode": "SO16 6TR", "area": "Bassett"}

    def reverse_geocode(self, latitude, longitude):
        return dict(self.place, latitude=latitude, longitude=longitude)

    def forward_geocode(self, description):
        return None


class FixtureTest(unittest.TestCase):
    def test_sixteen_cases_with_unique_names(self):
        cases = load_cases()
        self.assertEqual(len(cases), 16)
        self.assertEqual(len({case["name"] for case in cases}), 16)

    def test_every_case_has_the_required_shape(self):
        for case in load_cases():
            with self.subTest(case=case.get("name")):
                self.assertTrue(REQUIRED_CASE <= set(case), case.get("name"))
                self.assertIn(case["layer"], LAYERS)
                self.assertIn(case["legacy"], LEGACY)
                self.assertTrue(set(case) <= KNOWN_CASE, f"{case['name']}: unknown case key")
                expect = case["expect"]
                self.assertTrue(REQUIRED_EXPECT <= set(expect), case["name"])
                self.assertTrue(set(expect) <= KNOWN_EXPECT,
                                f"{case['name']}: unknown expect key")
                self.assertIsInstance(expect["rows"], int)
                for key in ("categories", "locations", "reply_contains", "reply_forbids"):
                    self.assertIsInstance(expect[key], list, f"{case['name']}:{key}")
                if "max_questions" in expect:
                    self.assertIsInstance(expect["max_questions"], int)

    def test_each_turn_has_text_or_a_photo_and_a_model_when_it_needs_one(self):
        for case in load_cases():
            for index, turn in enumerate(case["turns"]):
                with self.subTest(case=case["name"], turn=index):
                    self.assertTrue(turn.get("text") or turn.get("photo"), (case["name"], index))
                    if not turn.get("photo"):
                        self.assertIn("model", turn, (case["name"], index))

    def test_reply_rules_do_not_contradict_themselves(self):
        for case in load_cases():
            expect = case["expect"]
            overlap = set(expect["reply_contains"]) & set(expect["reply_forbids"])
            self.assertEqual(overlap, set(), case["name"])

    def test_graph_cases_declare_a_state_expectation(self):
        safety = {"info_question", "emergency_safe", "utility_safe", "outside_safe",
                  "trunk_road", "outside_city", "noise_handoff", "status_followup"}
        for case in load_cases():
            if case["layer"] == "graph" and case["name"] not in safety:
                with self.subTest(case=case["name"]):
                    self.assertTrue(
                        {"draft_preserved", "reroutes", "patch_preserved", "pending_resumed"}
                        & set(case["expect"]), case["name"])

    def test_graph_and_channel_cases_declare_a_gap(self):
        for case in load_cases():
            if case["layer"] in ("graph", "channel"):
                self.assertIn(case["legacy"], ("fail", "not_applicable", "unverified"),
                              case["name"])


class LegacyStatusTest(unittest.TestCase):
    """Run agent-layer cases against the current TriageAgent.

    A case marked legacy=fail must actually fail here. When the graph lands, the
    same case moves to the graph runner and this expectation flips.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = unittest.mock.patch.dict(
            os.environ, {"SOTONFIX_DB": str(Path(self.tmp.name) / "pin.db")})
        env.start()
        self.addCleanup(env.stop)
        for patcher in (
            unittest.mock.patch.object(tools._location_service, "forward_geocode", return_value=None),
            unittest.mock.patch.object(voice, "generate", return_value=None),
            unittest.mock.patch.object(location, "LocationService",
                                       lambda *args, **kwargs: FakeGeocoder()),
            unittest.mock.patch.object(O.photo, "start", return_value=None),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        old_notifier = getattr(O, "notify", None)
        O.set_notifier(lambda chat, text: None)
        self.addCleanup(O.set_notifier, old_notifier)
        self.clear_memory()
        self.addCleanup(self.clear_memory)

    @staticmethod
    def clear_memory():
        for store in (memory.PENDING, memory.PLACES, memory.CONTACTS):
            store.clear()

    @staticmethod
    def fake_chat(queue):
        def chat(system, user, image=None, **kwargs):
            if kwargs.get("purpose") == "triage" and queue:
                return json.dumps(queue.pop(0)), "model"
            return '{"facts": [], "answer": ""}', "model"
        return chat

    def run_case(self, case, sender="+447700900001"):
        case_dir = Path(tempfile.mkdtemp(dir=self.tmp.name))
        db_path = case_dir / "kerbside.db"
        reports_db.init_db(db_path, seed=False)
        queue = [dict(turn["model"]) for turn in case["turns"] if turn.get("model")]
        replies = []
        self.clear_memory()
        with unittest.mock.patch.object(reports_db, "DB_PATH", db_path), \
             unittest.mock.patch.dict(os.environ,
                                      {"SOTONFIX_DB": str(case_dir / "pin.db")}), \
             unittest.mock.patch.object(triage.llm, "chat",
                                        side_effect=self.fake_chat(queue)):
            for turn in case["turns"]:
                if turn.get("restart_before"):
                    self.clear_memory()   # a new process has no in-flight pending entry
                image = None
                photo = None
                if turn.get("photo"):
                    mime = turn["photo"]["mime"]
                    image = (b"jpeg", mime)
                    photo = (turn["photo"]["ref"], mime)
                outcome = O.handle(Turn(
                    sender=sender,
                    text=turn.get("text", ""),
                    chat="chat-" + sender,
                    image=image,
                    photo_ref=photo,
                    link_base="https://kerbside.test",
                ))
                replies.append(outcome.reply or "")
            self.assertEqual(queue, [], case["name"])   # a turn that skipped the model is visible
            conn = reports_db.connect(db_path)
            try:
                rows = [dict(row) for row in conn.execute(
                    "SELECT id, category_id, location, has_photo FROM reports ORDER BY id").fetchall()]
            finally:
                conn.close()
        return rows, replies

    def problems(self, case):
        rows, replies = self.run_case(case)
        expect = case["expect"]
        found = []
        if len(rows) != expect["rows"]:
            found.append(f"rows {len(rows)} != {expect['rows']}")
        categories = sorted(row["category_id"] for row in rows)
        if categories != sorted(expect["categories"]):
            found.append(f"categories {categories} != {expect['categories']}")
        locations = sorted(row["location"] for row in rows)
        if locations != sorted(expect["locations"]):
            found.append(f"locations {locations} != {expect['locations']}")
        last = replies[-1] if replies else ""
        for text in expect["reply_contains"]:
            if text not in last:
                found.append(f"last reply missing {text!r}")
        for text in expect["reply_forbids"]:
            if any(text in reply for reply in replies):
                found.append(f"reply contains {text!r}")
        for text in NEVER_SAID:
            if any(text in reply for reply in replies):
                found.append(f"reply contains {text!r} (global)")
        if "max_questions" in expect and last.count("?") > expect["max_questions"]:
            found.append(f"{last.count('?')} questions > {expect['max_questions']}")
        if "has_photo" in expect:
            photos = sum(int(row["has_photo"]) for row in rows)
            if photos != expect["has_photo"]:
                found.append(f"photos {photos} != {expect['has_photo']}")
        return found

    def test_agent_cases_match_their_recorded_legacy_status(self):
        for case in load_cases():
            if case["layer"] != "agent":
                continue
            with self.subTest(case=case["name"]):
                found = self.problems(case)
                print(f"[trajectory] {case['name']} legacy={case['legacy']} {found[:1]}")
                if case["legacy"] == "pass":
                    self.assertEqual(found, [], case["name"])
                else:
                    self.assertTrue(found, f"{case['name']} was expected to fail the legacy path")

    def test_the_graph_cases_are_listed_for_the_graph_runner(self):
        names = {case["name"] for case in load_cases()}
        for name in ("restart", "null_patch", "info_question", "emergency_safe",
                     "utility_safe", "outside_safe", "duplicate_webhook"):
            self.assertIn(name, names)


class GraphScaffoldTest(unittest.TestCase):
    def test_the_tree_case_saves_one_unclear_other_row(self):
        case = next(item for item in load_cases() if item["name"] == "tree_capture")
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "kerbside.db"
            store.migrate(db)
            runtime = TurnRuntime(Deps(
                threads=store.ThreadStore(db), playbooks={}, reports=db,
                ops=store.TurnOperations(db), outbox=store.Outbox(db),
                claims=store.Claims(db), writer=False), MemorySaver())
            result = runtime.turn({"sender": "+447700900002",
                                   "text": case["turns"][0]["text"],
                                   "message_guid": "g-tree"})
            self.assertEqual(result["kind"], "saved")
            self.assertIn("tree", result["state"]["incident_draft"]["description"])
            self.assertEqual(result["state"]["incident_draft"]["category_id"], "unclear_other")
            self.assertEqual(result["state"]["incident_draft"]["capture_state"], "captured")
            self.assertIn("hasn't gone to the council", " ".join(result["bubbles"]))
            conn = reports_db.connect(db)
            try:
                row = conn.execute("SELECT category_id, location FROM reports").fetchone()
            finally:
                conn.close()
            self.assertEqual(row["category_id"], "unclear_other")
            self.assertEqual(row["location"], "Not given")

    def test_the_remaining_graph_cases_are_named_not_skipped(self):
        covered = {"null_patch", "restart", "info_question", "emergency_safe",
                   "utility_safe", "outside_safe", "trunk_road", "outside_city",
                   "noise_handoff", "status_followup"}
        found = {item["name"] for item in load_cases() if item["layer"] == "graph"}
        self.assertEqual(found - covered, {"wrong_specialist"})


if __name__ == "__main__":
    unittest.main(verbosity=2)

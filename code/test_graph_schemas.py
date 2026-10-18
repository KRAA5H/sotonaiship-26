"""Tests for the graph contracts. Offline, no database, no model.

Run: python code/test_graph_schemas.py
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import voice  # noqa: E402
from graph import copy_rules, schemas  # noqa: E402
from graph.state import (ExecutedOutcome, IncidentDraft, ThreadState,  # noqa: E402
                         new_executed_outcome, new_incident_draft, new_thread_state)


def plan(**fields):
    base = {
        "dialogue_act": "new_report",
        "action": "log",
        "incident_patch": {"set": {"description": "pothole", "location": {"text": "Alma Road"}}},
        "service_candidates": ["pothole"],
        "specialist_request": None,
        "clarification": None,
        "fact_request": None,
        "escalation": None,
        "retracted_claims": [],
        "reason_codes": [],
    }
    base.update(fields)
    return base


def draft(**fields):
    item = new_incident_draft("pothole", {"text": "Alma Road"})
    item.update(fields)
    return item


def specialist(**fields):
    base = {
        "service_id": "pothole",
        "playbook_version": "v1",
        "fit": "supported",
        "observations": ["hole in the road"],
        "proposed_patch": {"set": {"severity": "medium"}},
        "missing_requirements": [],
        "suggested_question": None,
        "recommended_action": "log",
        "fact_ids": ["F1"],
        "source_refs": [{"url": "https://example.test/x", "date": "2026-10-17"}],
        "routing_status": "verified",
        "reason_codes": ["ok"],
    }
    base.update(fields)
    return base


def outcome(**fields):
    item = new_executed_outcome("log", saved=True)
    item.update({"report_id": "R-0001", "link_token": "a" * 16, "locally_actionable": True})
    item.update(fields)
    return item


class EnumTest(unittest.TestCase):
    def test_every_enum_is_unique_and_non_empty(self):
        for name in ("DIALOGUE_ACTS", "ACTIONS", "FITS", "CAPTURE_STATES", "ROUTING_STATUSES",
                     "PROVENANCE", "BUBBLE_PURPOSES", "TRANSPORT_STATES", "CATEGORY_OUTCOMES",
                     "SEVERITIES", "MESSAGE_ROLES", "ATTACHMENT_KINDS", "SPECIALIST_GROUPS",
                     "ESCALATION_KINDS", "CLEAR_REASONS"):
            with self.subTest(name=name):
                values = getattr(schemas, name)
                self.assertTrue(values)
                self.assertEqual(len(values), len(set(values)))

    def test_annotation_sets_match_the_contract(self):
        self.assertEqual(set(IncidentDraft.__annotations__), schemas.DRAFT_KEYS)
        self.assertEqual(set(ThreadState.__annotations__), schemas.STATE_KEYS)
        self.assertEqual(set(ExecutedOutcome.__annotations__), schemas.OUTCOME_KEYS)


class TurnPlanTest(unittest.TestCase):
    def test_log_ask_answer_and_escalate_pass(self):
        cases = [
            plan(),
            plan(action="ask", dialogue_act="new_report",
                 clarification={"field": "location", "reason": "need the street"}),
            plan(dialogue_act="question", action="answer", incident_patch={},
                 fact_request={"question": "how long for a pothole", "category_id": "pothole"}),
            plan(dialogue_act="other", action="escalate", incident_patch={},
                 escalation={"kind": "national_highways", "destination": "0300 123 5000"}),
        ]
        for index, case in enumerate(cases):
            with self.subTest(index=index):
                value, problems = schemas.validate_turn_plan(case)
                self.assertEqual(problems, [])
                self.assertIsNotNone(value)

    def test_unknown_enum_and_missing_action(self):
        _, problems = schemas.validate_turn_plan(plan(dialogue_act="meteor"))
        self.assertIn("schema.invalid:dialogue_act", problems)
        _, problems = schemas.validate_turn_plan({"dialogue_act": "new_report"})
        self.assertIn("action.missing", problems)

    def test_action_must_fit_the_dialogue_act(self):
        _, problems = schemas.validate_turn_plan(plan(dialogue_act="question", action="log"))
        self.assertIn("action.incompatible:log", problems)

    def test_ask_needs_exactly_one_clarification(self):
        _, problems = schemas.validate_turn_plan(plan(action="ask"))
        self.assertIn("ask.multiple_targets", problems)
        _, problems = schemas.validate_turn_plan(
            plan(action="ask", clarification=[{"field": "location"}, {"field": "photo"}]))
        self.assertIn("ask.multiple_targets", problems)
        _, problems = schemas.validate_turn_plan(
            plan(clarification={"field": "location", "reason": "x"}))
        self.assertIn("ask.unexpected", problems)

    def test_answer_needs_a_fact_request(self):
        _, problems = schemas.validate_turn_plan(
            plan(dialogue_act="question", action="answer", incident_patch={}))
        self.assertIn("schema.invalid:fact_request", problems)

    def test_a_model_cannot_escalate_to_999(self):
        _, problems = schemas.validate_turn_plan(
            plan(dialogue_act="other", action="escalate", incident_patch={},
                 escalation={"kind": "emergency_999", "destination": "999"}))
        self.assertIn("escalation.emergency_from_model", problems)

    def test_unknown_keys_and_unjustified_clear_are_rejected(self):
        _, problems = schemas.validate_turn_plan(plan(extra="x"))
        self.assertIn("schema.unknown_key:extra", problems)
        _, problems = schemas.validate_turn_plan(
            plan(incident_patch={"clear": ["severity"]}))
        self.assertIn("patch.clear_without_reason", problems)


class PatchShapeTest(unittest.TestCase):
    def test_patch_must_be_an_object_with_known_keys(self):
        for bad in (None, {}, {"location": {"text": "Alma Road"}}, {"replace": {}}):
            with self.subTest(bad=bad):
                _, problems = schemas.apply_patch(draft(), bad, 0)
                self.assertTrue(any("patch" in item for item in problems), problems)

    def test_unknown_set_add_or_clear_key_is_rejected(self):
        _, problems = schemas.apply_patch(draft(), {"set": {"photo": "x"}}, 0)
        self.assertIn("patch.unknown_key:photo", problems)
        _, problems = schemas.apply_patch(draft(), {"add": {"notes": []}}, 0)
        self.assertIn("patch.unknown_key:notes", problems)
        _, problems = schemas.apply_patch(
            draft(), {"clear": ["description"]}, 0, ["resident_correction"])
        self.assertIn("patch.unknown_key:description", problems)


class ApplyPatchTest(unittest.TestCase):
    def test_set_replaces_and_null_is_omitted(self):
        updated, problems = schemas.apply_patch(draft(), {"set": {"severity": "high"}}, 0)
        self.assertEqual(problems, [])
        self.assertEqual(updated["severity"], "high")
        self.assertEqual(updated["version"], 1)
        unchanged, problems = schemas.apply_patch(draft(), {"set": {"severity": None}}, 0)
        self.assertEqual(problems, ["patch.no_change"])
        self.assertEqual(unchanged["version"], 0)

    def test_empty_values_cannot_erase_a_report(self):
        cases = [
            ({"set": {"description": ""}}, "patch.empty_value:description"),
            ({"set": {"location": {"text": ""}}}, "patch.empty_value:location.text"),
            ({"set": {"location": {"street": ""}}}, "patch.empty_value:location.street"),
        ]
        for patch, expected in cases:
            with self.subTest(patch=patch):
                _, problems = schemas.apply_patch(draft(), patch, 0)
                self.assertIn(expected, problems)

    def test_append_only_fields_dedupe(self):
        photo = {"kind": "photo", "ref": "guid:1"}
        claim = {"claim": "flooding", "reason": "wrong", "at": "2026-10-18"}
        updated, problems = schemas.apply_patch(
            draft(), {"add": {"attachments": [photo, photo], "retracted": [claim, claim]}}, 0)
        self.assertEqual(problems, [])
        self.assertEqual(len(updated["attachments"]), 1)
        self.assertEqual(len(updated["retracted"]), 1)

    def test_clear_needs_a_real_reason(self):
        _, problems = schemas.apply_patch(draft(), {"clear": ["severity"]}, 0)
        self.assertIn("patch.clear_without_reason", problems)
        _, problems = schemas.apply_patch(draft(), {"clear": ["severity"]}, 0, ["because"])
        self.assertIn("patch.clear_without_reason", problems)

    def test_clear_location_only_when_empty_or_not_given(self):
        filled = draft()
        _, problems = schemas.apply_patch(filled, {"clear": ["location"]}, 0, ["resident_correction"])
        self.assertIn("patch.protected:location", problems)
        for text in ("Not given", "not given", "  Not given "):
            with self.subTest(text=text):
                item = new_incident_draft("tree", {"text": text})
                updated, problems = schemas.apply_patch(
                    item, {"clear": ["location"]}, 0, ["resident_correction"])
                self.assertEqual(problems, [])
                self.assertEqual(updated["location"]["text"], "")

    def test_version_is_required_and_stale_versions_are_refused(self):
        with self.assertRaises(TypeError):
            schemas.apply_patch(draft(), {})
        _, problems = schemas.apply_patch(draft(), {"set": {"severity": "low"}}, 99)
        self.assertEqual(problems, ["patch.stale_version"])

    def test_input_is_not_mutated_and_output_validates(self):
        original = draft()
        before = repr(original)
        updated, problems = schemas.apply_patch(original, {"set": {"description": "deep hole"}}, 0)
        self.assertEqual(problems, [])
        self.assertEqual(repr(original), before)
        self.assertEqual(schemas.validate_incident_draft(updated)[1], [])

    def test_policy_fields_have_one_writer(self):
        _, problems = schemas.apply_patch(
            draft(), {"set": {"capture_state": "verified"}}, 0)
        self.assertIn("patch.unknown_key:capture_state", problems)
        updated, problems = schemas.set_policy_fields(
            draft(), capture_state="locally_actionable",
            routing_status="verified", reason="address checked")
        self.assertEqual(problems, [])
        self.assertEqual(updated["capture_state"], "locally_actionable")
        self.assertEqual(updated["routing_status"], "verified")
        _, problems = schemas.set_policy_fields(draft(), routing_status="verified")
        self.assertEqual(problems, ["policy.reason_required"])


class BubblePlanTest(unittest.TestCase):
    def test_a_good_plan_passes(self):
        value, problems = schemas.validate_bubble_plan({
            "bubbles": [{"purpose": "action", "text": "i've saved that here."}],
            "url": "https://kerbside.test/r/" + "a" * 16,
            "suppressed": False,
        })
        self.assertEqual(problems, [])
        self.assertIsNotNone(value)

    def test_counts_and_copy_are_checked(self):
        bad = [
            {"bubbles": []},
            {"bubbles": [{"purpose": "action", "text": "x"}] * 4},
            {"bubbles": [{"purpose": "action", "text": "see https://evil.test"}]},
            {"bubbles": [{"purpose": "action", "text": "see www.example.test"}]},
            {"bubbles": [{"purpose": "action", "text": "**bold**"}]},
            {"bubbles": [{"purpose": "action", "text": "a \u2014 b"}]},
            {"bubbles": [{"purpose": "action", "text": "a \u2013 b"}]},
            {"bubbles": [{"purpose": "action", "text": "report R-0001"}]},
            {"bubbles": [{"purpose": "action", "text": "x" * 301}]},
            {"bubbles": [{"purpose": "meteor", "text": "x"}]},
        ]
        for case in bad:
            with self.subTest(case=case):
                _, problems = schemas.validate_bubble_plan(case)
                self.assertTrue(problems, case)

    def test_url_must_be_a_private_report_link(self):
        for url in ("/council", "https://kerbside.test/r/R-0001",
                    "https://kerbside.test/council/r/" + "a" * 16):
            with self.subTest(url=url):
                _, problems = schemas.validate_bubble_plan(
                    {"bubbles": [{"purpose": "action", "text": "saved"}], "url": url})
                self.assertIn("schema.invalid:url", problems)

    def test_suppressed_needs_permission(self):
        suppressed = {"bubbles": [], "url": None, "suppressed": True}
        _, problems = schemas.validate_bubble_plan(suppressed)
        self.assertIn("schema.invalid:suppressed", problems)
        value, problems = schemas.validate_bubble_plan(suppressed, allow_suppressed=True)
        self.assertEqual(problems, [])
        self.assertTrue(value["suppressed"])


class SpecialistTest(unittest.TestCase):
    def test_a_supported_result_passes(self):
        value, problems = schemas.validate_specialist_result(specialist())
        self.assertEqual(problems, [])
        self.assertIsNotNone(value)

    def test_supported_needs_sources_and_facts(self):
        _, problems = schemas.validate_specialist_result(
            specialist(source_refs=[], fact_ids=[]))
        self.assertIn("specialist.unsupported:sources", problems)

    def test_mismatch_needs_observations(self):
        _, problems = schemas.validate_specialist_result(
            specialist(fit="mismatch", observations=[]))
        self.assertIn("specialist.unsupported:observations", problems)

    def test_bad_dates_facts_and_actions_are_rejected(self):
        _, problems = schemas.validate_specialist_result(
            specialist(source_refs=[{"url": "https://example.test/x", "date": "2030-01-01"}]))
        self.assertIn("schema.invalid:source_refs", problems)
        _, problems = schemas.validate_specialist_result(specialist(fact_ids=["X1"]))
        self.assertIn("schema.invalid:fact_ids", problems)
        _, problems = schemas.validate_specialist_result(specialist(recommended_action="send"))
        self.assertIn("schema.invalid:recommended_action", problems)

    def test_a_specialist_patch_obeys_the_same_rules(self):
        _, problems = schemas.validate_specialist_result(
            specialist(proposed_patch={"set": {"description": ""}}))
        self.assertTrue(any("patch" in item or "empty" in item for item in problems), problems)


class OutcomeTest(unittest.TestCase):
    def test_saved_and_refused_outcomes_are_representable(self):
        self.assertEqual(schemas.validate_executed_outcome(outcome())[1], [])
        refused = new_executed_outcome("log", saved=False, refused_reason="no_location")
        self.assertEqual(schemas.validate_executed_outcome(refused)[1], [])

    def test_saved_needs_a_report_and_refused_needs_a_reason(self):
        _, problems = schemas.validate_executed_outcome(outcome(report_id=None))
        self.assertIn("schema.invalid:report_id", problems)
        _, problems = schemas.validate_executed_outcome(
            new_executed_outcome("log", saved=False))
        self.assertIn("schema.invalid:refused_reason", problems)

    def test_transport_and_facts_are_checked(self):
        _, problems = schemas.validate_executed_outcome(outcome(transport="teleported"))
        self.assertIn("schema.invalid:transport", problems)
        _, problems = schemas.validate_executed_outcome(
            outcome(facts=[{"fact": "x", "url": "ftp://x", "date": "2026-10-17"}]))
        self.assertIn("schema.invalid:fact", problems)


class ThreadStateTest(unittest.TestCase):
    def test_a_new_state_validates(self):
        value, problems = schemas.validate_thread_state(new_thread_state("h-1", "g-1"))
        self.assertEqual(problems, [])
        self.assertIsNotNone(value)

    def test_recent_messages_are_capped_and_typed(self):
        state = new_thread_state("h-1", "g-1")
        state["recent_messages"] = [{"role": "resident", "text": "x"}] * 13
        _, problems = schemas.validate_thread_state(state)
        self.assertIn("schema.invalid:recent_messages", problems)
        state["recent_messages"] = [{"role": "meteor", "text": "x"}]
        _, problems = schemas.validate_thread_state(state)
        self.assertIn("schema.invalid:message.role", problems)

    def test_nested_plan_and_outcome_are_validated(self):
        state = new_thread_state("h-1", "g-1")
        state["plan"] = plan(dialogue_act="meteor")
        _, problems = schemas.validate_thread_state(state)
        self.assertIn("schema.invalid:dialogue_act", problems)


class CopyRulesTest(unittest.TestCase):
    def test_copy_rules_match_voice(self):
        self.assertEqual(copy_rules.MAX_CHARS, voice.MAX_CHARS)
        self.assertEqual(copy_rules.MARKDOWN.pattern, voice.MARKDOWN.pattern)
        self.assertEqual(copy_rules.URLISH.pattern, voice.URLISH.pattern)
        self.assertEqual(copy_rules.REPORT_ID.pattern, voice.REPORT_ID.pattern)
        self.assertEqual(copy_rules.EM_DASH, voice.EM_DASH)
        self.assertEqual(copy_rules.EN_DASH, "\u2013")

    def test_the_contract_layer_imports_no_runtime(self):
        base = Path(__file__).resolve().parent / "graph"
        for name in ("state.py", "schemas.py", "copy_rules.py", "__init__.py"):
            source = (base / name).read_text(encoding="utf-8")
            for forbidden in ("import llm", "import voice", "langgraph", "sqlite3",
                              "import requests", "import flask"):
                with self.subTest(file=name, forbidden=forbidden):
                    self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main(verbosity=2)

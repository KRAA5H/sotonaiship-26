"""Tests for the graph policy gate. Offline, pure, no database.

Run: python code/test_graph_policy.py
"""

import sys
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from graph import policy, schemas  # noqa: E402
from graph.state import (new_executed_outcome, new_incident_draft,  # noqa: E402
                         new_thread_state)


def plan(**fields):
    base = {
        "dialogue_act": "new_report",
        "action": "log",
        "incident_patch": {"set": {"severity": "medium"}},
        "service_candidates": [],
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
    item = new_incident_draft("pothole on Alma Road", {"text": "Alma Road"})
    item["category_id"] = "pothole"
    item.update(fields)
    return item


def captured(**fields):
    item = new_incident_draft("tree down across the road", {"text": ""})
    item["category_id"] = "unclear_other"
    item.update(fields)
    return item


def make(the_plan=None, the_draft=None, **fields):
    state = new_thread_state("h-1", "g-1")
    if the_draft is not None:
        state["incident_draft"] = the_draft
    if the_plan is not None:
        state["plan"] = the_plan
    state.update(fields)
    return state


CONTEXT = policy.PolicyContext(
    known_categories=frozenset({
        "pothole", "unclear_other", "flooding_severe_weather", "not_council_utility",
        "outside_southampton", "noise_nuisance", "fly_tipping",
    }),
    category_outcomes={
        "pothole": "council_report",
        "unclear_other": "council_report",
        "flooding_severe_weather": "info_only",
        "not_council_utility": "not_council",
        "outside_southampton": "not_council",
        "noise_nuisance": "council_report",
    },
    known_facts={"https://example.test/fact": "2026-10-17"},
    allowed_destinations=frozenset({"0300 123 5000", "999"}),
    allowed_questions=frozenset({"location", "description", "photo"}),
    allowed_numbers=frozenset({"0300 123 5000"}),
    forbidden_team_names=frozenset({"Highways Team"}),
)


def codes(violations):
    return [item["code"] for item in violations]


class CapturePolicyTest(unittest.TestCase):
    def test_a_captured_incident_passes(self):
        self.assertEqual(policy.check(
            make(the_plan=plan(), the_draft=captured()), CONTEXT), [])

    def test_no_description_and_no_photo_is_capture_lost(self):
        item = captured(description="")
        self.assertIn("capture.lost",
                      codes(policy.check(make(the_plan=plan(), the_draft=item), CONTEXT)))

    def test_a_fresh_ask_for_a_description_passes(self):
        the_plan = plan(action="ask", incident_patch=None,
                        clarification={"field": "description", "reason": "what is wrong"})
        self.assertEqual(policy.check(
            make(the_plan=the_plan, the_draft=new_incident_draft()), CONTEXT), [])

    def test_a_photo_only_capture_passes(self):
        item = captured(description="", attachments=[{"kind": "photo", "ref": "guid:1"}])
        self.assertEqual(policy.check(make(the_plan=plan(), the_draft=item), CONTEXT), [])

    def test_never_saved_categories_are_refused(self):
        for category in ("outside_southampton", "not_council_trunk_road", "not_council_utility"):
            with self.subTest(category=category):
                item = captured(category_id=category)
                self.assertIn("not_council.saved",
                              codes(policy.check(make(the_plan=plan(), the_draft=item), CONTEXT)))

    def test_a_patch_cannot_smuggle_a_never_saved_category(self):
        the_plan = plan(incident_patch={"set": {"category_id": "not_council_utility"}})
        self.assertIn("not_council.saved",
                      codes(policy.check(make(the_plan=the_plan, the_draft=draft()), CONTEXT)))

    def test_a_patch_cannot_clear_a_filled_location(self):
        the_plan = plan(incident_patch={"clear": ["location"]},
                        reason_codes=["resident_correction"])
        self.assertIn("patch.protected",
                      codes(policy.check(make(the_plan=the_plan, the_draft=draft()), CONTEXT)))

    def test_a_patch_cannot_change_to_an_info_only_category(self):
        the_plan = plan(incident_patch={"set": {"category_id": "flooding_severe_weather"}})
        self.assertIn("policy.category_unknown",
                      codes(policy.check(make(the_plan=the_plan, the_draft=draft()), CONTEXT)))

    def test_info_only_logged_directly_is_a_category_error(self):
        item = captured(category_id="flooding_severe_weather")
        self.assertIn("policy.category_unknown",
                      codes(policy.check(make(the_plan=plan(), the_draft=item), CONTEXT)))

    def test_a_handoff_category_must_not_log(self):
        item = captured(category_id="noise_nuisance")
        self.assertIn("policy.handoff_action",
                      codes(policy.check(make(the_plan=plan(), the_draft=item), CONTEXT)))

    def test_an_unknown_category_is_repairable_to_the_catch_all(self):
        item = captured(category_id="tree")
        problems = policy.check(make(the_plan=plan(), the_draft=item), CONTEXT)
        self.assertIn("policy.category_unknown", codes(problems))
        self.assertTrue(policy.can_repair(problems))

    def test_no_category_for_a_log_is_an_error(self):
        item = captured(category_id=None)
        self.assertIn("policy.category_unknown",
                      codes(policy.check(make(the_plan=plan(), the_draft=item), CONTEXT)))

    def test_routing_status_must_be_needs_review_for_unclear_other(self):
        item = captured(routing_status="verified")
        self.assertIn("policy.routing_unverified",
                      codes(policy.check(make(the_plan=plan(), the_draft=item), CONTEXT)))

    def test_a_specialist_mismatch_blocks_the_plan(self):
        state = make(the_plan=plan(), the_draft=draft(),
                     specialist_results=[{"service_id": "pothole", "fit": "mismatch",
                                          "observations": ["it is a tree"]}])
        self.assertIn("policy.specialist_mismatch", codes(policy.check(state, CONTEXT)))


class QuestionPolicyTest(unittest.TestCase):
    def ask(self, field):
        return plan(action="ask", incident_patch=None,
                    clarification={"field": field, "reason": "needed"})

    def test_ask_cannot_repeat_a_known_location(self):
        self.assertIn("ask.known_field", codes(policy.check(
            make(the_plan=self.ask("location"), the_draft=draft()), CONTEXT)))

    def test_ask_can_request_a_location_that_is_not_given(self):
        item = new_incident_draft("tree", {"text": "Not given"})
        item["category_id"] = "unclear_other"
        self.assertEqual(policy.check(
            make(the_plan=self.ask("location"), the_draft=item), CONTEXT), [])

    def test_ask_allows_an_ambiguous_location(self):
        item = draft()
        item["location"]["ambiguous"] = True
        self.assertEqual(policy.check(
            make(the_plan=self.ask("location"), the_draft=item), CONTEXT), [])

    def test_ask_allows_a_missing_house_number(self):
        context = replace(CONTEXT, missing_fields=frozenset({"location"}))
        self.assertEqual(policy.check(
            make(the_plan=self.ask("location"), the_draft=draft()), context), [])

    def test_ask_cannot_repeat_a_known_description(self):
        self.assertIn("ask.known_field", codes(policy.check(
            make(the_plan=self.ask("description"), the_draft=draft()), CONTEXT)))

    def test_an_unknown_question_is_refused(self):
        self.assertIn("policy.question_unknown", codes(policy.check(
            make(the_plan=self.ask("favourite_colour"), the_draft=draft()), CONTEXT)))

    def test_a_repeated_pending_question_is_refused(self):
        state = make(the_plan=self.ask("location"), the_draft=captured(),
                     pending_question={"field": "location", "text": "where is it",
                                       "asked_at": "2026-10-18T00:00:00+00:00",
                                       "turn_id": "g-0"})
        self.assertIn("policy.question_repeated", codes(policy.check(state, CONTEXT)))


class CorrectionPolicyTest(unittest.TestCase):
    def challenge(self, claims, sent):
        state = make(the_plan=plan(dialogue_act="challenge_previous_claim",
                                   retracted_claims=claims, incident_patch=None),
                     the_draft=captured())
        state["last_claims_sent"] = sent
        return policy.check(state, CONTEXT)

    def test_a_challenge_must_name_a_claim(self):
        problems = self.challenge([], ["sorry, flooding is not a report"])
        self.assertIn("retraction.missing", codes(problems))
        self.assertTrue(all(item["hard"] for item in problems
                            if item["code"] == "retraction.missing"))

    def test_a_challenge_with_nothing_sent_is_hard(self):
        problems = self.challenge(["flooding"], [])
        self.assertTrue(all(item["hard"] for item in problems
                            if item["code"] == "retraction.missing"))

    def test_a_challenge_must_match_a_positive_claim(self):
        problems = self.challenge(["flooding"], ["i've saved your pothole report"])
        self.assertIn("retraction.missing", codes(problems))
        self.assertFalse(any(item["hard"] for item in problems
                             if item["code"] == "retraction.missing"))

    def test_a_denial_is_not_a_claim(self):
        problems = self.challenge(["flooding"], ["we can't help with flooding"])
        self.assertIn("retraction.missing", codes(problems))

    def test_a_matching_challenge_passes(self):
        self.assertEqual(self.challenge(["flooding"], ["we logged it as flooding"]), [])

    def test_a_noop_correction_is_refused(self):
        item = make(the_plan=plan(dialogue_act="correction", incident_patch=None),
                    the_draft=draft())
        self.assertIn("policy.correction_noop", codes(policy.check(item, CONTEXT)))

    def test_a_severity_only_correction_is_refused(self):
        item = make(the_plan=plan(dialogue_act="correction",
                                  incident_patch={"set": {"severity": "high"}}),
                    the_draft=draft())
        self.assertIn("policy.correction_noop", codes(policy.check(item, CONTEXT)))

    def test_a_description_correction_passes(self):
        item = make(the_plan=plan(dialogue_act="correction",
                                  incident_patch={"set": {"description": "it is a tree"}}),
                    the_draft=draft())
        self.assertEqual(policy.check(item, CONTEXT), [])


class EscalationPolicyTest(unittest.TestCase):
    def escalate(self, destination, kind="national_highways"):
        return plan(action="escalate", incident_patch=None,
                    escalation={"kind": kind, "destination": destination})

    def test_an_unknown_destination_is_hard(self):
        problems = policy.check(make(the_plan=self.escalate("https://evil.test"),
                                     the_draft=draft()), CONTEXT)
        self.assertIn("policy.destination_unknown", codes(problems))
        self.assertTrue(all(item["hard"] for item in problems
                            if item["code"] == "policy.destination_unknown"))

    def test_999_is_only_for_an_emergency(self):
        problems = policy.check(make(the_plan=self.escalate("999", "emergency_999"),
                                     the_draft=draft()), CONTEXT)
        self.assertIn("escalation.emergency_from_model", codes(problems))

    def test_an_emergency_cannot_log_or_patch(self):
        state = make(the_plan=plan(action="log"), the_draft=captured(), emergency=True)
        self.assertIn("emergency.tools", codes(policy.check(state, CONTEXT)))
        state = make(the_plan=plan(action="answer",
                                   incident_patch={"set": {"severity": "high"}}),
                     the_draft=captured(), emergency=True)
        self.assertIn("emergency.tools", codes(policy.check(state, CONTEXT)))

    def test_an_emergency_can_escalate_to_999(self):
        state = make(the_plan=self.escalate("999", "emergency_999"),
                     the_draft=captured(), emergency=True)
        self.assertEqual(policy.check(state, CONTEXT), [])

    def test_a_short_circuit_greeting_can_ask(self):
        state = make(the_plan=plan(action="ask", incident_patch=None,
                                   clarification={"field": "description",
                                                  "reason": "what is wrong"}),
                     the_draft=new_incident_draft(), short_circuit=True)
        self.assertEqual(policy.check(state, CONTEXT), [])

    def test_a_suppressed_turn_passes(self):
        state = make(the_plan=plan(action="log"), the_draft=captured(), suppressed=True)
        self.assertEqual(policy.check(state, CONTEXT), [])


class BudgetPolicyTest(unittest.TestCase):
    def test_a_repairable_violation_gets_one_repair(self):
        problems = [policy._violation("ask.known_field", "clarification")]
        self.assertEqual(policy.decide(problems, repair_count=0), "repair")
        self.assertEqual(policy.decide(problems, repair_count=1), "fallback")

    def test_a_specialist_request_with_no_budget_is_hard(self):
        state = make(the_plan=plan(specialist_request={"group": "highways", "reason": "check"}),
                     the_draft=draft(), specialist_call_count=2)
        self.assertIn("budget.exceeded", codes(policy.check(state, CONTEXT)))

    def test_too_many_specialist_results_is_hard(self):
        state = make(the_plan=plan(), the_draft=draft(),
                     specialist_results=[{}, {}, {}])
        self.assertIn("budget.exceeded", codes(policy.check(state, CONTEXT)))

    def test_more_than_one_repair_is_hard(self):
        state = make(the_plan=plan(), the_draft=draft(), repair_count=2)
        self.assertIn("budget.exceeded", codes(policy.check(state, CONTEXT)))

    def test_the_model_call_budget_is_capped(self):
        state = make(the_plan=plan(), the_draft=draft(), model_calls=5)
        self.assertIn("budget.exceeded", codes(policy.check(state, CONTEXT)))


class OutcomePolicyTest(unittest.TestCase):
    def outcome(self, **fields):
        item = new_executed_outcome("log", saved=True)
        item.update({"report_id": "R-0001", "link_token": "a" * 16,
                     "locally_actionable": True,
                     "facts": [{"fact": "x", "url": "https://example.test/fact",
                                "date": "2026-10-17"}]})
        item.update(fields)
        return item

    def test_a_clean_outcome_passes(self):
        self.assertEqual(policy.check_outcome(self.outcome(), draft(), CONTEXT), [])

    def test_a_submitted_outcome_cannot_claim_receipt(self):
        self.assertIn("claim.council_receipt",
                      codes(policy.check_outcome(self.outcome(submitted=True), draft(), CONTEXT)))

    def test_locally_actionable_without_a_location(self):
        item = new_incident_draft("tree", {"text": "Not given"})
        self.assertIn("capture.no_location",
                      codes(policy.check_outcome(self.outcome(), item, CONTEXT)))

    def test_a_pin_only_location_is_actionable(self):
        item = new_incident_draft("tree", {"text": "", "street": "Alma Road",
                                           "provenance": "pin"})
        self.assertEqual(policy.check_outcome(self.outcome(), item, CONTEXT), [])

    def test_an_unknown_fact_url_is_hard(self):
        bad = self.outcome(facts=[{"fact": "x", "url": "https://evil.test",
                                   "date": "2026-10-17"}])
        self.assertIn("policy.fact_unknown", codes(policy.check_outcome(bad, draft(), CONTEXT)))

    def test_a_wrong_fact_date_is_hard(self):
        bad = self.outcome(facts=[{"fact": "x", "url": "https://example.test/fact",
                                   "date": "1999-01-01"}])
        self.assertIn("policy.fact_date", codes(policy.check_outcome(bad, draft(), CONTEXT)))

    def test_an_answer_may_write_nothing(self):
        good = new_executed_outcome("answer")
        self.assertEqual(policy.check_outcome(good, draft(), CONTEXT), [])


class BubblePolicyTest(unittest.TestCase):
    def test_council_receipt_and_timescale_claims(self):
        self.assertIn("claim.council_receipt",
                      codes(policy.check_bubbles(["the council has it"], None, CONTEXT)))
        self.assertIn("claim.timescale",
                      codes(policy.check_bubbles(["a crew will be out within 2 hours"],
                                                 None, CONTEXT)))

    def test_numbers_and_team_names(self):
        self.assertIn("claim.number",
                      codes(policy.check_bubbles(["call 01234 567890"], None, CONTEXT)))
        self.assertIn("claim.team",
                      codes(policy.check_bubbles(["Highways Team will fix it"], None, CONTEXT)))
        self.assertEqual(policy.check_bubbles(["call 0300 123 5000"], None, CONTEXT), [])


class DecisionTest(unittest.TestCase):
    def test_decide(self):
        self.assertEqual(policy.decide([]), "execute")
        self.assertEqual(policy.decide([policy._violation("ask.known_field")]), "repair")
        self.assertEqual(policy.decide([policy._violation("capture.lost")]), "fallback")
        self.assertEqual(policy.decide([policy._violation("capture.lost"),
                                        policy._violation("ask.known_field")]), "fallback")

    def test_can_repair_and_hard_failures(self):
        soft = [policy._violation("ask.known_field")]
        hard = [policy._violation("capture.lost")]
        self.assertTrue(policy.can_repair(soft))
        self.assertFalse(policy.can_repair(hard))
        self.assertEqual(policy.hard_failures(soft + hard), hard)


class ContractTest(unittest.TestCase):
    def test_a_non_dict_plan_does_not_crash(self):
        state = new_thread_state("h-1", "g-1")
        state["plan"] = "not a plan"
        self.assertIn("policy.plan_missing", codes(policy.check(state, CONTEXT)))

    def test_schema_problems_are_merged(self):
        state = new_thread_state("h-1", "g-1")
        found = codes(policy.check(state, CONTEXT, problems=["schema.unknown_key:extra"]))
        self.assertIn("schema.unknown_key", found)
        self.assertIn("policy.plan_missing", found)

    def test_violations_round_trip_through_thread_state(self):
        state = make(the_plan=plan(action="ask", incident_patch=None,
                                   clarification={"field": "location", "reason": "where"}),
                     the_draft=draft())
        state["violations"] = policy.check(state, CONTEXT)
        self.assertTrue(state["violations"])
        self.assertEqual(schemas.validate_thread_state(state)[1], [])

    def test_every_problem_code_is_classified(self):
        classified = set(policy.REPAIRABLE) | set(policy.HARD) | set(policy.DEFERRED)
        missing = set(schemas.PROBLEM_CODES) - classified
        self.assertEqual(missing, set())


class IsolationTest(unittest.TestCase):
    def test_the_policy_imports_no_runtime(self):
        source = (Path(__file__).resolve().parent / "graph" / "policy.py").read_text(
            encoding="utf-8")
        for forbidden in ("import llm", "import tools", "import reports_db",
                          "import requests", "import sqlite3", "import flask",
                          "import agents", "from agents"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_the_sentinel_matches_the_schema(self):
        self.assertEqual(policy.LOCATION_UNKNOWN, schemas.LOCATION_UNKNOWN)


if __name__ == "__main__":
    unittest.main(verbosity=2)

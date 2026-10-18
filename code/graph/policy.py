"""The graph policy gate: deterministic invariants between a plan and a write.

Pure functions. No database, no model, no network. The caller supplies the
categories, facts and destinations it knows; a `None` context field defers that
check to a later step.

The policy judges the **effective** incident after the plan's patch is applied,
so a plan cannot smuggle a forbidden category or a cleared location past the
check and then have `execute` apply it.
"""

import re
from dataclasses import dataclass
from typing import Mapping

from . import schemas

LOCATION_UNKNOWN = "Not given"

REPAIRABLE = frozenset({
    "schema.invalid", "schema.unknown_key", "action.incompatible", "ask.unexpected",
    "ask.known_field", "ask.multiple_targets",
    "policy.category_unknown", "policy.correction_noop", "policy.handoff_action",
    "policy.question_unknown", "policy.question_repeated", "policy.reason_required",
    "retraction.missing",
    "patch.unknown_key", "patch.empty_value", "patch.clear_without_reason",
    "patch.no_change",
})
HARD = frozenset({
    "capture.lost", "capture.no_location", "not_council.saved", "emergency.tools",
    "policy.short_circuit_action", "budget.exceeded",
    "claim.council_receipt", "claim.team", "claim.number", "claim.timescale",
    "policy.fact_unknown", "policy.fact_date", "policy.answer_ungrounded",
    "policy.destination_unknown", "policy.specialist_mismatch",
    "policy.routing_unverified", "escalation.emergency_from_model",
    "action.missing", "policy.plan_missing", "patch.stale_version", "patch.protected",
    "specialist.unsupported",
})
# Raised by later steps, listed so every schema code has an owner.
DEFERRED = frozenset({"copy.lines", "copy.urls", "copy.markdown", "copy.banned",
                      "duplicate.unverified", "bubble.empty", "bubble.too_many"})

_NEGATION = re.compile(r"\b(not|can't|cannot|isn't|wasn't|no)\b", re.I)
_COUNCIL_RECEIPT = re.compile(
    r"\b(the council has|the council have|with the council|council is looking|"
    r"council has it|council have it|council got it|council received|council will)\b",
    re.I)
_TIMESCALE = re.compile(
    r"\bwithin\s+\d+|\bin\s+\d+\s*(hour|day|week)|\b(tonight|tomorrow|today|this week)\b"
    r"|\bcrew will\b", re.I)
_NUMBER = re.compile(r"\b0\d{2,4}\s?\d{3,4}\s?\d{0,4}\b")
_TRUNK_TEXT = re.compile(r"\b(A3[36]|M27|M3|motorway|trunk road)\b", re.I)
_OUTSIDE_TEXT = re.compile(r"\b(winchester|eastleigh|fareham|portsmouth|gosport|romsey|outside southampton)\b(?!\s+(?:road|street|lane|avenue|close|drive|way|crescent|gardens|hill|park|terrace|place|grove|court|walk|mews|rise|row)\b)", re.I)
_HANDOFF_TEXT = re.compile(
    r"\b(noisy (neighbour|neighbor)|neighbour(s)? (noise|making noise)|loud music|"
    r"barking dog|noise from (next door|the neighbours?)|noise nuisance)\b", re.I)
_UTILITY_TEXT = re.compile(r"\b(power cut|electricity|water leak|gas leak)\b", re.I)


@dataclass(frozen=True)
class PolicyContext:
    known_categories: frozenset[str] | None = None
    category_outcomes: Mapping[str, str] | None = None
    known_facts: Mapping[str, str] | None = None          # url -> date_checked
    allowed_destinations: frozenset[str] | None = None
    allowed_questions: frozenset[str] | None = None
    allowed_numbers: frozenset[str] | None = None
    forbidden_team_names: frozenset[str] | None = None
    missing_fields: frozenset[str] | None = None
    required_local: frozenset[str] | None = None
    location_mode: str | None = None
    handoff_categories: frozenset[str] = frozenset(
        {"noise_nuisance", "other_nuisance", "property_concern"})
    never_saved: frozenset[str] = frozenset(
        {"outside_southampton", "not_council_trunk_road", "not_council_utility"})


def _violation(code, field=None, message="", hard=None):
    if hard is None:
        hard = code in HARD or code not in REPAIRABLE
    return {"code": code, "field": field, "message": message, "hard": bool(hard)}


def violation_from_problem(problem):
    """Turn a schema problem string (`code` or `code:field`) into a violation."""
    code, _, field = str(problem).partition(":")
    return _violation(code or "schema.invalid", field or None, str(problem))


def _dedupe(violations):
    seen = set()
    unique = []
    for item in violations:
        key = (item["code"], item["field"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _has_place(draft):
    """A street, address or postcode. A district name alone is not a place to act on."""
    location = draft.get("location") or {}
    for key in ("text", "street", "postcode"):
        value = location.get(key)
        if isinstance(value, str) and value.strip() \
                and value.strip().lower() != LOCATION_UNKNOWN.lower():
            return True
    return False


def _has_evidence(draft):
    return bool((draft.get("description") or "").strip()) or bool(draft.get("attachments"))


def _category(plan, draft):
    return draft.get("category_id") or ((plan.get("service_candidates") or [None])[0])


def _catches(category, context):
    found = []
    if not category:
        found.append(_violation("policy.category_unknown", "category_id",
                                "no category candidate"))
        return found
    if category in context.never_saved:
        found.append(_violation("not_council.saved", "category_id",
                                f"{category} is never saved"))
    outcome = (context.category_outcomes or {}).get(category)
    if outcome == "not_council":
        found.append(_violation("not_council.saved", "category_id",
                                f"{category} is not the council's"))
    if outcome == "info_only" and category != "unclear_other":
        found.append(_violation("policy.category_unknown", "category_id",
                                f"{category} is information-only; capture as unclear_other"))
    if context.known_categories and category not in context.known_categories \
            and category != "unclear_other":
        found.append(_violation("policy.category_unknown", "category_id",
                                f"{category} is not in the rulebook"))
    return found


def _sent_claim(claim, sent):
    """True when the claim appears in a positive clause we actually sent."""
    needle = " ".join(str(claim).lower().split())
    for item in sent:
        for clause in re.split(r"[,.;!?]|\bbut\b", str(item).lower()):
            if needle and needle in clause and not _NEGATION.search(clause):
                return True
    return False


def _patch_violations(draft, plan):
    """Apply the plan patch and return (effective draft, violations)."""
    patch = plan.get("incident_patch") or {}
    if not patch:
        return draft, []
    effective, problems = schemas.apply_patch(
        draft, patch, draft.get("version", 0), plan.get("reason_codes"))
    if not problems or problems == ["patch.no_change"]:
        return effective, []
    violations = []
    for problem in problems:
        code = problem.split(":")[0]
        hard = code in ("patch.stale_version", "patch.protected", "schema.invalid")
        violations.append(_violation(code, "incident_patch", problem, hard=hard))
    return draft, violations


def check(state, context=PolicyContext(), problems=()):
    """Return the violations that stop this plan. Empty means it may execute."""
    violations = [violation_from_problem(item) for item in problems]
    if state.get("suppressed"):
        return []
    plan = state.get("plan")
    if not isinstance(plan, dict) or not plan:
        violations.append(_violation("policy.plan_missing", "plan",
                                     "no plan to validate"))
        return _dedupe(violations)
    draft = state.get("incident_draft") or {}
    action = plan.get("action")
    patch = plan.get("incident_patch") or {}
    target = (plan.get("clarification") or {}).get("field")
    emergency = bool(state.get("emergency"))
    short = bool(state.get("short_circuit"))

    if emergency:
        if action not in ("answer", "escalate"):
            violations.append(_violation("emergency.tools", "action",
                                         "an emergency cannot log or ask"))
        if any(patch.get(key) for key in ("set", "clear", "add")) \
                or plan.get("specialist_request"):
            violations.append(_violation("emergency.tools", "plan",
                                         "an emergency cannot patch or call a specialist"))
        return _dedupe(violations)

    if short:
        if action == "log" or any(patch.get(key) for key in ("set", "clear", "add")) \
                or plan.get("specialist_request"):
            violations.append(_violation("policy.short_circuit_action", "plan",
                                         "a greeting or status turn cannot log or patch"))
        return _dedupe(violations)

    if action not in ("log", "ask", "answer", "escalate"):
        violations.append(_violation("action.missing", "action", "unknown action"))
        return _dedupe(violations)

    text = (state.get("inbound") or {}).get("text") or ""
    if action in ("log", "ask"):
        if _TRUNK_TEXT.search(text) or _OUTSIDE_TEXT.search(text)                 or _UTILITY_TEXT.search(text):
            violations.append(_violation("not_council.saved", "inbound",
                                         "a trunk road, utility or out-of-area issue is never saved",
                                         hard=True))
        if _HANDOFF_TEXT.search(text):
            violations.append(_violation("policy.handoff_action", "inbound",
                                         "a neighbour problem goes to the council form",
                                         hard=True))

    effective, patch_violations = _patch_violations(draft, plan)
    violations += patch_violations

    if action == "log" and not _has_evidence(effective):
        violations.append(_violation("capture.lost", "incident_draft",
                                     "no description or photo to keep"))
    if action == "ask" and not _has_evidence(effective) and target != "description":
        violations.append(_violation("capture.lost", "incident_draft",
                                     "no description or photo to keep"))

    if action in ("log", "ask"):
        category = _category(plan, effective)
        if category:
            violations += _catches(category, context)
        elif action == "log":
            violations += _catches(None, context)
        proposed = (plan.get("service_candidates") or [None])[0]
        if proposed and proposed != category:
            # A candidate is not the write target. A wrong label is repairable,
            # never a hard never-save that kills a valid capture.
            if proposed in context.never_saved \
                    or (context.category_outcomes or {}).get(proposed) == "not_council":
                violations.append(_violation("policy.category_unknown", "service_candidates",
                                             f"{proposed} is not the write target"))
            elif context.known_categories and proposed not in context.known_categories \
                    and proposed != "unclear_other":
                violations.append(_violation("policy.category_unknown", "service_candidates",
                                             f"{proposed} is not in the rulebook"))
        if category in context.handoff_categories and action == "log":
            violations.append(_violation("policy.handoff_action", "category_id",
                                         "neighbour problems use the council form, not a log"))
        if category == "unclear_other" \
                and effective.get("routing_status") != "needs_review":
            violations.append(_violation("policy.routing_unverified", "routing_status",
                                         "an unclear capture cannot claim verified routing"))
        latest = (state.get("specialist_results") or [None])[-1]
        if latest and latest.get("fit") == "mismatch" \
                and latest.get("service_id") == category:
            violations.append(_violation("policy.specialist_mismatch", "specialist_results",
                                         "a mismatched specialist still owns the plan"))

    if action == "ask":
        ambiguous = bool((effective.get("location") or {}).get("ambiguous"))
        still_missing = bool(context.missing_fields and target in context.missing_fields)
        if target == "location" and _has_place(effective) \
                and not ambiguous and not still_missing:
            violations.append(_violation("ask.known_field", "clarification",
                                         "the street is already known"))
        if target == "description" and (effective.get("description") or "").strip():
            violations.append(_violation("ask.known_field", "clarification",
                                         "the description is already known"))
        if context.allowed_questions and target not in context.allowed_questions:
            violations.append(_violation("policy.question_unknown", "clarification",
                                         f"{target} is not a question this service asks"))
        pending = state.get("pending_question") or {}
        if pending.get("field") == target and pending.get("text"):
            violations.append(_violation("policy.question_repeated", "clarification",
                                         "the same field was already asked"))

    if action == "answer":
        category = (plan.get("fact_request") or {}).get("category_id")
        if category and category != "general" \
                and context.known_categories and category not in context.known_categories:
            violations.append(_violation("policy.category_unknown", "fact_request",
                                         f"{category} is not in the rulebook"))

    if action == "escalate":
        escalation = plan.get("escalation") or {}
        destination = escalation.get("destination")
        if context.allowed_destinations and destination not in context.allowed_destinations:
            violations.append(_violation("policy.destination_unknown", "escalation",
                                         "the destination is not in the checked list"))
        if escalation.get("kind") == "emergency_999" and not emergency:
            violations.append(_violation("escalation.emergency_from_model", "escalation",
                                         "only precheck may escalate to 999"))

    if plan.get("dialogue_act") == "challenge_previous_claim":
        claims = plan.get("retracted_claims") or []
        sent = state.get("last_claims_sent") or []
        if not claims:
            violations.append(_violation("retraction.missing", "retracted_claims",
                                         "a challenge must name what it retracts", hard=True))
        elif not sent:
            violations.append(_violation("retraction.missing", "last_claims_sent",
                                         "nothing was sent to retract", hard=True))
        else:
            for claim in claims:
                if not _sent_claim(claim, sent):
                    violations.append(_violation("retraction.missing", "retracted_claims",
                                                 f"{claim!r} was not in a positive claim"))

    if plan.get("dialogue_act") == "correction":
        substantive = set((patch.get("set") or {})) & {"description", "location", "category_id"}
        if not substantive:
            violations.append(_violation("policy.correction_noop", "incident_patch",
                                         "a correction must change the problem, place or category"))

    if state.get("repair_count", 0) > 1:
        violations.append(_violation("budget.exceeded", "repair_count",
                                     "more than one repair attempt"))
    if state.get("specialist_call_count", 0) > 2:
        violations.append(_violation("budget.exceeded", "specialist_call_count",
                                     "more than two specialist calls"))
    if len(state.get("specialist_results") or []) > 2:
        violations.append(_violation("budget.exceeded", "specialist_results",
                                     "more than two specialist results"))
    if plan.get("specialist_request") and state.get("specialist_call_count", 0) >= 2:
        violations.append(_violation("budget.exceeded", "specialist_request",
                                     "no budget for another specialist"))
    if state.get("model_calls", 0) > 4:
        violations.append(_violation("budget.exceeded", "model_calls",
                                     "more than four model calls in a turn"))
    return _dedupe(violations)


def check_outcome(outcome, draft=None, context=PolicyContext()):
    """Check what actually happened before the writer describes it."""
    violations = []
    if outcome.get("submitted") is True:
        violations.append(_violation("claim.council_receipt", "submitted",
                                     "no submission integration exists"))
    if outcome.get("locally_actionable") and draft is not None:
        required = context.required_local
        if required is None:
            required = frozenset({"description", "location"})
        if "description" in required and not (draft.get("description") or "").strip():
            violations.append(_violation("capture.lost", "description",
                                         "locally actionable without a description"))
        if {"location", "address"} & set(required) and not _has_place(draft):
            violations.append(_violation("capture.no_location", "location",
                                         "locally actionable without a street or postcode"))
    if outcome.get("action") == "answer" and not outcome.get("facts") \
            and not outcome.get("report_id") and not outcome.get("link_token"):
        violations.append(_violation("policy.answer_ungrounded", "facts",
                                     "an answer needs a checked fact or a record"))
    if context.known_facts:
        for fact in outcome.get("facts") or []:
            url, date = fact.get("url"), fact.get("date")
            if url not in context.known_facts:
                violations.append(_violation("policy.fact_unknown", "facts",
                                             "a fact URL is not in the checked sheet"))
                break
            if context.known_facts[url] != date:
                violations.append(_violation("policy.fact_date", "facts",
                                             "a fact date is not the checked date"))
                break
    return _dedupe(violations)


def check_bubbles(bubbles, outcome=None, context=PolicyContext()):
    """Claim checks over the writer's text. Step 9's lint is the full copy gate."""
    violations = []
    submitted = bool((outcome or {}).get("submitted"))
    for text in bubbles or []:
        if not submitted and _COUNCIL_RECEIPT.search(text):
            violations.append(_violation("claim.council_receipt", "bubbles",
                                         "a local report cannot claim council receipt"))
        if _TIMESCALE.search(text):
            violations.append(_violation("claim.timescale", "bubbles",
                                         "no timescale was executed"))
        for number in _NUMBER.findall(text):
            if context.allowed_numbers is not None and number not in context.allowed_numbers:
                violations.append(_violation("claim.number", "bubbles",
                                             "a number is not in the checked sheet"))
        if context.forbidden_team_names:
            lowered = text.lower()
            if "national highways" in lowered:
                lowered = lowered.replace("national highways", " ")
            for team in context.forbidden_team_names:
                if team.lower() in lowered:
                    violations.append(_violation("claim.team", "bubbles",
                                                 f"{team} is not confirmed"))
    return _dedupe(violations)


def can_repair(violations):
    return bool(violations) and not any(item["hard"] for item in violations)


def hard_failures(violations):
    return [item for item in violations if item["hard"]]


def decide(violations, repair_count=0):
    if not violations:
        return "execute"
    if any(item["hard"] for item in violations):
        return "fallback"
    if repair_count < 1:
        return "repair"
    return "fallback"

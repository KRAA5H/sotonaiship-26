"""Graph contracts: enums, validators and patch semantics.

Pure functions. No database, no network, no model. Strings returned in `problems`
are `code` or `code:field`, so the policy and repair nodes can act on them.
"""

import copy
import datetime
import re

from . import copy_rules
from .state import MAX_RECENT_MESSAGES, empty_location

DIALOGUE_ACTS = ("new_report", "detail", "correction", "challenge_previous_claim",
                 "question", "status", "greeting", "other")
ACTIONS = ("log", "ask", "answer", "escalate")
FITS = ("supported", "uncertain", "mismatch")
CAPTURE_STATES = ("captured", "locally_actionable", "submission_ready", "submitted")
ROUTING_STATUSES = ("needs_review", "verified")
PROVENANCE = ("text", "pin", "gps", "postcode", "none")
BUBBLE_PURPOSES = ("repair", "question", "action", "tracking")
TRANSPORT_STATES = ("queued", "sent", "failed", "ambiguous")
CATEGORY_OUTCOMES = ("council_report", "info_only", "not_council")
SEVERITIES = ("high", "medium", "low")
MESSAGE_ROLES = ("resident", "agent")
ATTACHMENT_KINDS = ("photo",)
SPECIALIST_GROUPS = ("cleansing", "highways", "waste", "housing")
ESCALATION_KINDS = ("emergency_999", "national_highways", "utility",
                    "council_complaints", "council_out_of_hours",
                    "adult_social_care", "council_finder", "council_form")
CLEAR_REASONS = ("resident_correction", "new_incident", "wrong_place", "no_longer_relevant")
LOCATION_UNKNOWN = "Not given"

PROBLEM_CODES = (
    "schema.invalid", "schema.unknown_key", "action.missing", "action.incompatible",
    "ask.multiple_targets", "ask.unexpected", "ask.known_field", "capture.lost",
    "claim.council_receipt", "claim.team", "claim.number", "claim.timescale",
    "copy.lines", "copy.urls", "copy.markdown", "copy.banned", "retraction.missing",
    "emergency.tools", "not_council.saved", "duplicate.unverified", "budget.exceeded",
    "patch.unknown_key", "patch.empty_value", "patch.protected",
    "patch.clear_without_reason", "patch.stale_version", "patch.no_change",
    "escalation.emergency_from_model", "specialist.unsupported", "bubble.empty",
    "bubble.too_many", "policy.reason_required",
)

PLAN_KEYS = {"dialogue_act", "action", "incident_patch", "service_candidates",
             "specialist_request", "clarification", "fact_request", "escalation",
             "retracted_claims", "reason_codes", "profile_patch", "task_request"}
PROFILE_KEYS = {"name", "address", "phone", "style"}
TASK_KEYS = {"kind", "fields"}
TASK_KINDS = ("permit", "council_tax", "bins")
PATCH_KEYS = {"set", "clear", "add"}
PATCHABLE = {"category_id", "category_candidates", "description", "location", "severity"}
APPENDABLE = {"attachments", "evidence", "retracted"}
CLEARABLE = {"category_id", "category_candidates", "severity", "location"}
LOCATION_KEYS = {"text", "street", "area", "postcode", "provenance", "ambiguous"}
ATTACHMENT_KEYS = {"kind", "ref", "features"}
CANDIDATE_KEYS = {"id", "confidence"}
DRAFT_KEYS = {"id", "capture_state", "routing_status", "category_candidates",
              "category_id", "description", "location", "attachments", "severity",
              "evidence", "retracted", "version"}
INBOUND_KEYS = {"sender", "chat", "text", "message_guid", "image_ref", "photo_ref", "card"}
MESSAGE_KEYS = {"role", "text", "at"}
PENDING_KEYS = {"field", "text", "asked_at", "turn_id"}
OUTCOME_KEYS = {"action", "report_id", "link_token", "submitted", "duplicate_of",
                "locally_actionable", "missing", "facts", "review_queued",
                "transport", "degraded", "saved", "refused_reason",
                "playbook_version", "destination", "status", "location_url",
                "task_url"}
STATE_KEYS = {"thread_id", "turn_id", "inbound", "recent_messages", "active_incident_id",
              "incident_draft", "pending_question", "profile", "conversation",
              "task", "last_claims_sent",
              "last_executed_outcome", "candidate_services", "selected_specialist",
              "specialist_results", "plan", "violations", "executed_outcome",
              "bubble_plan", "review_queued", "repair_count", "specialist_call_count",
              "delivery_outbox_ids", "degraded", "short_circuit", "emergency",
              "suppressed", "model_calls"}
SPECIALIST_KEYS = {"service_id", "playbook_version", "fit", "observations",
                   "proposed_patch", "missing_requirements", "suggested_question",
                   "recommended_action", "fact_ids", "source_refs", "routing_status",
                   "reason_codes"}
BUBBLE_PLAN_KEYS = {"bubbles", "url", "source_url", "suppressed"}
BUBBLE_KEYS = {"purpose", "text"}
CLARIFICATION_KEYS = {"field", "reason"}
FACT_REQUEST_KEYS = {"question", "category_id"}
SPECIALIST_REQUEST_KEYS = {"group", "reason"}
ESCALATION_KEYS = {"kind", "destination"}
EVIDENCE_KEYS = {"kind", "ref", "text", "at", "source"}
RETRACTED_KEYS = {"claim", "reason", "at"}
VIOLATION_KEYS = {"code", "field", "message", "hard"}

COMPATIBLE = {
    "new_report": {"log", "ask"},
    "detail": {"log", "ask"},
    "correction": {"log", "ask"},
    "challenge_previous_claim": {"log", "ask", "answer"},
    "question": {"answer", "escalate"},
    "status": {"answer"},
    "greeting": {"ask", "answer"},
    "other": {"answer", "ask", "escalate"},
}

_REPORT_ID = re.compile(r"^R-\d{4}$")
_FACT_ID = re.compile(r"^F\d+$")
_TOKEN = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_LINK = re.compile(r"^https?://[^/\s]+/r/[A-Za-z0-9_-]{16,}$")


def _problem(code, field=None):
    return f"{code}:{field}" if field else code


def _text(value, limit=400):
    if not isinstance(value, str):
        return None
    return " ".join(value.replace("\x00", " ").split())[:limit]


def _unknown(obj, allowed, code="schema.unknown_key"):
    return [_problem(code, key) for key in obj if key not in allowed]


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_http(value):
    return isinstance(value, str) and value.startswith(("http://", "https://")) and " " not in value


def _is_date(value, today=None):
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.date.fromisoformat(value)
    except ValueError:
        return False
    return parsed <= (today or datetime.date.today())


def _string_list(value):
    return isinstance(value, list) and all(isinstance(item, str) and item.strip() for item in value)


def _validate_patch_shape(patch):
    problems = []
    if not isinstance(patch, dict):
        return ["patch.unknown_key"]
    if not patch:
        return ["patch.unknown_key"]
    problems += _unknown(patch, PATCH_KEYS, "patch.unknown_key")
    sets = patch.get("set")
    adds = patch.get("add")
    for key, value, allowed in (("set", sets, PATCHABLE), ("add", adds, APPENDABLE)):
        if value is None:
            continue
        if not isinstance(value, dict):
            problems.append(_problem("patch.unknown_key", key))
            continue
        problems += _unknown(value, allowed, "patch.unknown_key")
    clear = patch.get("clear")
    if clear is not None:
        if not isinstance(clear, list):
            problems.append(_problem("patch.unknown_key", "clear"))
        else:
            for field in clear:
                if field not in CLEARABLE:
                    problems.append(_problem("patch.unknown_key", str(field)))
    for field, value in (sets if isinstance(sets, dict) else {}).items():
        if field == "description" and not (isinstance(value, str) or value is None):
            problems.append(_problem("schema.invalid", "set.description"))
        elif field == "description" and isinstance(value, str) and not value.strip():
            problems.append(_problem("patch.empty_value", "description"))
        elif field == "category_id" and not (isinstance(value, str) or value is None):
            problems.append(_problem("schema.invalid", "set.category_id"))
        elif field == "category_id" and isinstance(value, str) and not value.strip():
            problems.append(_problem("patch.empty_value", "category_id"))
        elif field == "category_candidates" and not isinstance(value, list):
            problems.append(_problem("schema.invalid", "set.category_candidates"))
        elif field == "location" and not isinstance(value, dict):
            problems.append(_problem("schema.invalid", "set.location"))
        elif field == "location":
            problems += _unknown(value, LOCATION_KEYS)
            for key in ("text", "street", "area", "postcode"):
                item = value.get(key)
                if isinstance(item, str) and not item.strip():
                    problems.append(_problem("patch.empty_value", f"location.{key}"))
        elif field == "severity" and not (isinstance(value, str) or value is None):
            problems.append(_problem("schema.invalid", "set.severity"))
    for field, value in (adds if isinstance(adds, dict) else {}).items():
        if not isinstance(value, list):
            problems.append(_problem("schema.invalid", f"add.{field}"))
            continue
        for item in value:
            if field == "attachments":
                if not isinstance(item, dict) or set(item) - ATTACHMENT_KEYS \
                        or item.get("kind") not in ATTACHMENT_KINDS \
                        or not _text(item.get("ref")):
                    problems.append(_problem("schema.invalid", "attachments"))
            elif field == "evidence":
                if not isinstance(item, dict) or set(item) - EVIDENCE_KEYS:
                    problems.append(_problem("schema.invalid", "evidence"))
            elif field == "retracted":
                if not isinstance(item, dict) or set(item) - RETRACTED_KEYS \
                        or not _text(item.get("claim")):
                    problems.append(_problem("schema.invalid", "retracted"))
    return problems


def validate_turn_plan(raw, allow_emergency=False):
    if not isinstance(raw, dict):
        return None, ["schema.invalid"]
    problems = _unknown(raw, PLAN_KEYS)
    dialogue_act = raw.get("dialogue_act")
    action = raw.get("action")
    if dialogue_act not in DIALOGUE_ACTS:
        problems.append(_problem("schema.invalid", "dialogue_act"))
    if action not in ACTIONS:
        problems.append("action.missing")
    if dialogue_act in DIALOGUE_ACTS and action in ACTIONS and action not in COMPATIBLE[dialogue_act]:
        problems.append(_problem("action.incompatible", action))

    patch = raw.get("incident_patch")
    if patch is not None:
        problems += _validate_patch_shape(patch)
    candidates = raw.get("service_candidates") or []
    if not _string_list(candidates):
        problems.append(_problem("schema.invalid", "service_candidates"))

    specialist = raw.get("specialist_request")
    if specialist is not None:
        if not isinstance(specialist, dict):
            problems.append(_problem("schema.invalid", "specialist_request"))
        else:
            problems += _unknown(specialist, SPECIALIST_REQUEST_KEYS)
            if specialist.get("group") not in SPECIALIST_GROUPS:
                problems.append(_problem("schema.invalid", "specialist_request.group"))
            if not _text(specialist.get("reason")):
                problems.append(_problem("schema.invalid", "specialist_request.reason"))

    clarification = raw.get("clarification")
    if action == "ask":
        if not isinstance(clarification, dict):
            problems.append("ask.multiple_targets")
        else:
            problems += _unknown(clarification, CLARIFICATION_KEYS)
            if not _text(clarification.get("field")):
                problems.append(_problem("schema.invalid", "clarification.field"))
            if not _text(clarification.get("reason")):
                problems.append(_problem("schema.invalid", "clarification.reason"))
    elif clarification is not None:
        problems.append("ask.unexpected")

    fact_request = raw.get("fact_request")
    if action == "answer":
        if not isinstance(fact_request, dict):
            problems.append(_problem("schema.invalid", "fact_request"))
        else:
            problems += _unknown(fact_request, FACT_REQUEST_KEYS)
            if not _text(fact_request.get("question")):
                problems.append(_problem("schema.invalid", "fact_request.question"))
    elif fact_request is not None:
        problems.append(_problem("schema.invalid", "fact_request"))

    escalation = raw.get("escalation")
    if action == "escalate":
        if not isinstance(escalation, dict):
            problems.append(_problem("schema.invalid", "escalation"))
        else:
            problems += _unknown(escalation, ESCALATION_KEYS)
            kind = escalation.get("kind")
            if kind not in ESCALATION_KINDS:
                problems.append(_problem("schema.invalid", "escalation.kind"))
            if kind == "emergency_999" and not allow_emergency:
                problems.append("escalation.emergency_from_model")
            if not _text(escalation.get("destination")):
                problems.append(_problem("schema.invalid", "escalation.destination"))
    elif escalation is not None:
        problems.append(_problem("schema.invalid", "escalation"))

    task_request = raw.get("task_request")
    if task_request is not None:
        if not isinstance(task_request, dict):
            problems.append(_problem("schema.invalid", "task_request"))
        else:
            problems += _unknown(task_request, TASK_KEYS)
            if task_request.get("kind") not in TASK_KINDS:
                problems.append(_problem("schema.invalid", "task_request.kind"))
            fields = task_request.get("fields") or {}
            if not isinstance(fields, dict):
                problems.append(_problem("schema.invalid", "task_request.fields"))
            else:
                for key, value in fields.items():
                    if not isinstance(key, str) or not isinstance(value, str):
                        problems.append(_problem("schema.invalid", "task_request.fields"))

    profile_patch = raw.get("profile_patch")
    if profile_patch is not None:
        if not isinstance(profile_patch, dict):
            problems.append(_problem("schema.invalid", "profile_patch"))
        else:
            problems += _unknown(profile_patch, PROFILE_KEYS)
            for key, value in profile_patch.items():
                if value is not None and not isinstance(value, str):
                    problems.append(_problem("schema.invalid", f"profile_patch.{key}"))
            if profile_patch.get("style") not in (None, "casual", "formal"):
                problems.append(_problem("schema.invalid", "profile_patch.style"))

    retracted = raw.get("retracted_claims") or []
    if not _string_list(retracted):
        problems.append(_problem("schema.invalid", "retracted_claims"))
    reasons = raw.get("reason_codes") or []
    if not _string_list(reasons):
        problems.append(_problem("schema.invalid", "reason_codes"))
    if patch and (patch.get("clear") or []) and not reasons:
        problems.append("patch.clear_without_reason")

    if problems:
        return None, problems
    return {
        "dialogue_act": dialogue_act,
        "action": action,
        "incident_patch": patch or {},
        "service_candidates": candidates,
        "specialist_request": specialist,
        "clarification": clarification,
        "fact_request": fact_request,
        "escalation": escalation,
        "retracted_claims": retracted,
        "reason_codes": reasons,
        "profile_patch": profile_patch or {},
        "task_request": task_request,
    }, []


def validate_specialist_result(raw, today=None):
    if not isinstance(raw, dict):
        return None, ["schema.invalid"]
    problems = _unknown(raw, SPECIALIST_KEYS)
    if not _text(raw.get("service_id")):
        problems.append(_problem("schema.invalid", "service_id"))
    fit = raw.get("fit")
    if fit not in FITS:
        problems.append(_problem("schema.invalid", "fit"))
    observations = raw.get("observations") or []
    if not _string_list(observations):
        problems.append(_problem("schema.invalid", "observations"))
    if fit == "mismatch" and not observations:
        problems.append(_problem("specialist.unsupported", "observations"))
    problems += _validate_patch_shape(raw.get("proposed_patch")) \
        if raw.get("proposed_patch") is not None else []
    if not _string_list(raw.get("missing_requirements") or []):
        problems.append(_problem("schema.invalid", "missing_requirements"))
    suggested = raw.get("suggested_question")
    if suggested is not None and not _text(suggested):
        problems.append(_problem("schema.invalid", "suggested_question"))
    if raw.get("recommended_action") not in ACTIONS:
        problems.append(_problem("schema.invalid", "recommended_action"))
    fact_ids = raw.get("fact_ids") or []
    if not all(isinstance(item, str) and _FACT_ID.match(item) for item in fact_ids):
        problems.append(_problem("schema.invalid", "fact_ids"))
    refs = raw.get("source_refs") or []
    if not isinstance(refs, list):
        problems.append(_problem("schema.invalid", "source_refs"))
        refs = []
    for ref in refs:
        if not isinstance(ref, dict) or not _is_http(ref.get("url")) or not _is_date(ref.get("date"), today):
            problems.append(_problem("schema.invalid", "source_refs"))
            break
    if fit == "supported" and (not refs or not fact_ids):
        problems.append(_problem("specialist.unsupported", "sources"))
    if raw.get("routing_status") not in ROUTING_STATUSES:
        problems.append(_problem("schema.invalid", "routing_status"))
    if not _string_list(raw.get("reason_codes") or []):
        problems.append(_problem("schema.invalid", "reason_codes"))
    if problems:
        return None, problems
    return raw, []


def validate_bubble_plan(raw, allow_suppressed=False):
    if not isinstance(raw, dict):
        return None, ["schema.invalid"]
    problems = _unknown(raw, BUBBLE_PLAN_KEYS)
    url = raw.get("url")
    if url is not None and not (isinstance(url, str) and _LINK.match(url)):
        problems.append(_problem("schema.invalid", "url"))
    source_url = raw.get("source_url")
    if source_url is not None and not (
            isinstance(source_url, str) and source_url.startswith(("http://", "https://"))
            and " " not in source_url):
        problems.append(_problem("schema.invalid", "source_url"))
    suppressed = raw.get("suppressed", False)
    bubbles = raw.get("bubbles")
    if suppressed:
        if not allow_suppressed:
            problems.append(_problem("schema.invalid", "suppressed"))
        if bubbles not in ([], None):
            problems.append(_problem("bubble.empty", "suppressed"))
        if url is not None:
            problems.append(_problem("schema.invalid", "url"))
    else:
        if not isinstance(bubbles, list) or not bubbles:
            problems.append("bubble.empty")
        elif len(bubbles) > copy_rules.MAX_BUBBLES:
            problems.append("bubble.too_many")
        else:
            for bubble in bubbles:
                if not isinstance(bubble, dict):
                    problems.append(_problem("schema.invalid", "bubble"))
                    continue
                problems += _unknown(bubble, BUBBLE_KEYS)
                if bubble.get("purpose") not in BUBBLE_PURPOSES:
                    problems.append(_problem("schema.invalid", "bubble.purpose"))
                text = bubble.get("text")
                if not isinstance(text, str) or not text.strip():
                    problems.append("bubble.empty")
                    continue
                if "\n" in text or "\r" in text:
                    problems.append(_problem("copy.lines", "bubble"))
                if len(text) > copy_rules.MAX_CHARS:
                    problems.append(_problem("copy.lines", "too_long"))
                if copy_rules.MARKDOWN.search(text):
                    problems.append("copy.markdown")
                if copy_rules.EM_DASH in text or copy_rules.EN_DASH in text:
                    problems.append("copy.banned")
                if copy_rules.URLISH.search(text):
                    problems.append("copy.urls")
                if copy_rules.REPORT_ID.search(text):
                    problems.append(_problem("copy.banned", "report_id"))
    if problems:
        return None, problems
    return {"bubbles": bubbles or [], "url": url, "source_url": source_url,
            "suppressed": bool(suppressed)}, []


def validate_incident_draft(raw):
    if not isinstance(raw, dict):
        return None, ["schema.invalid"]
    problems = _unknown(raw, DRAFT_KEYS)
    if raw.get("capture_state") not in CAPTURE_STATES:
        problems.append(_problem("schema.invalid", "capture_state"))
    if raw.get("routing_status") not in ROUTING_STATUSES:
        problems.append(_problem("schema.invalid", "routing_status"))
    if not isinstance(raw.get("description", ""), str):
        problems.append(_problem("schema.invalid", "description"))
    if raw.get("category_id") is not None and not isinstance(raw.get("category_id"), str):
        problems.append(_problem("schema.invalid", "category_id"))
    if raw.get("severity") is not None and raw.get("severity") not in SEVERITIES:
        problems.append(_problem("schema.invalid", "severity"))
    if raw.get("id") is not None and not isinstance(raw.get("id"), str):
        problems.append(_problem("schema.invalid", "id"))
    if not _is_int(raw.get("version", 0)) or raw.get("version", 0) < 0:
        problems.append(_problem("schema.invalid", "version"))

    location = raw.get("location")
    if not isinstance(location, dict):
        problems.append(_problem("schema.invalid", "location"))
    else:
        problems += _unknown(location, LOCATION_KEYS)
        if location.get("provenance") not in PROVENANCE:
            problems.append(_problem("schema.invalid", "location.provenance"))
        for key in ("lat", "lng", "latitude", "longitude"):
            if key in location:
                problems.append(_problem("schema.invalid", f"location.{key}"))

    attachments = raw.get("attachments") or []
    if not isinstance(attachments, list):
        problems.append(_problem("schema.invalid", "attachments"))
    else:
        for item in attachments:
            if not isinstance(item, dict) or item.get("kind") not in ATTACHMENT_KINDS \
                    or not _text(item.get("ref")):
                problems.append(_problem("schema.invalid", "attachment"))
                break
            if set(item) - ATTACHMENT_KEYS:
                problems.append(_problem("schema.invalid", "attachment.keys"))
                break

    candidates = raw.get("category_candidates") or []
    if not isinstance(candidates, list):
        problems.append(_problem("schema.invalid", "category_candidates"))
    else:
        for item in candidates:
            if not isinstance(item, dict) or not _text(item.get("id")) \
                    or not _is_number(item.get("confidence", 0)) \
                    or not 0 <= item.get("confidence", 0) <= 1:
                problems.append(_problem("schema.invalid", "category_candidate"))
                break

    for name, allowed in (("evidence", EVIDENCE_KEYS), ("retracted", RETRACTED_KEYS)):
        items = raw.get(name) or []
        if not isinstance(items, list):
            problems.append(_problem("schema.invalid", name))
            continue
        for item in items:
            if not isinstance(item, dict) or set(item) - allowed:
                problems.append(_problem("schema.invalid", name))
                break
            for key in ("lat", "lng", "latitude", "longitude", "phone"):
                if key in item:
                    problems.append(_problem("schema.invalid", f"{name}.{key}"))
                    break
    if problems:
        return None, problems
    return copy.deepcopy(raw), []


def validate_executed_outcome(raw):
    if not isinstance(raw, dict):
        return None, ["schema.invalid"]
    problems = _unknown(raw, OUTCOME_KEYS)
    if raw.get("action") not in ACTIONS:
        problems.append(_problem("schema.invalid", "action"))
    report_id = raw.get("report_id")
    if report_id is not None and not (isinstance(report_id, str) and _REPORT_ID.match(report_id)):
        problems.append(_problem("schema.invalid", "report_id"))
    token = raw.get("link_token")
    if token is not None and not (isinstance(token, str) and _TOKEN.match(token)):
        problems.append(_problem("schema.invalid", "link_token"))
    duplicate = raw.get("duplicate_of")
    if duplicate is not None and not (isinstance(duplicate, str) and _REPORT_ID.match(duplicate)):
        problems.append(_problem("schema.invalid", "duplicate_of"))
    for field in ("submitted", "locally_actionable", "review_queued", "saved"):
        if not isinstance(raw.get(field), bool):
            problems.append(_problem("schema.invalid", field))
    if not _string_list(raw.get("missing") or []):
        problems.append(_problem("schema.invalid", "missing"))
    if not _string_list(raw.get("degraded") or []):
        problems.append(_problem("schema.invalid", "degraded"))
    if raw.get("transport") not in TRANSPORT_STATES:
        problems.append(_problem("schema.invalid", "transport"))
    facts = raw.get("facts") or []
    if not isinstance(facts, list):
        problems.append(_problem("schema.invalid", "facts"))
    else:
        for fact in facts:
            if not isinstance(fact, dict) or not _text(fact.get("fact")) \
                    or not _is_http(fact.get("url")) or not _is_date(fact.get("date")):
                problems.append(_problem("schema.invalid", "fact"))
                break
    if raw.get("playbook_version") is not None and not _text(raw.get("playbook_version")):
        problems.append(_problem("schema.invalid", "playbook_version"))
    saved = raw.get("saved")
    if saved is True and report_id is None:
        problems.append(_problem("schema.invalid", "report_id"))
    if saved is False:
        if report_id is not None:
            problems.append(_problem("schema.invalid", "report_id"))
        if raw.get("action") == "log" and not _text(raw.get("refused_reason")):
            problems.append(_problem("schema.invalid", "refused_reason"))
    if problems:
        return None, problems
    return copy.deepcopy(raw), []


def validate_thread_state(raw, today=None):
    if not isinstance(raw, dict):
        return None, ["schema.invalid"]
    problems = _unknown(raw, STATE_KEYS)
    if not _text(raw.get("thread_id")) or not _text(raw.get("turn_id")):
        problems.append(_problem("schema.invalid", "thread_id"))
    if not isinstance(raw.get("inbound", {}), dict):
        problems.append(_problem("schema.invalid", "inbound"))
    else:
        problems += _unknown(raw.get("inbound") or {}, INBOUND_KEYS)
    messages = raw.get("recent_messages") or []
    if not isinstance(messages, list) or len(messages) > MAX_RECENT_MESSAGES:
        problems.append(_problem("schema.invalid", "recent_messages"))
    else:
        for item in messages:
            if not isinstance(item, dict) or item.get("role") not in MESSAGE_ROLES:
                problems.append(_problem("schema.invalid", "message.role"))
                break
            if set(item) - MESSAGE_KEYS:
                problems.append(_problem("schema.invalid", "message.keys"))
                break
    draft, draft_problems = validate_incident_draft(raw.get("incident_draft") or {})
    problems += draft_problems
    pending = raw.get("pending_question")
    if pending is not None:
        if not isinstance(pending, dict):
            problems.append(_problem("schema.invalid", "pending_question"))
        else:
            problems += _unknown(pending, PENDING_KEYS)
            if not _text(pending.get("field")) or not _text(pending.get("text")):
                problems.append(_problem("schema.invalid", "pending_question"))
    if not _string_list(raw.get("last_claims_sent") or []):
        problems.append(_problem("schema.invalid", "last_claims_sent"))
    if not _string_list(raw.get("candidate_services") or []):
        problems.append(_problem("schema.invalid", "candidate_services"))
    if not _string_list(raw.get("delivery_outbox_ids") or []):
        problems.append(_problem("schema.invalid", "delivery_outbox_ids"))
    if not _string_list(raw.get("degraded") or []):
        problems.append(_problem("schema.invalid", "degraded"))
    for field in ("repair_count", "specialist_call_count"):
        if not _is_int(raw.get(field, 0)) or raw.get(field, 0) < 0:
            problems.append(_problem("schema.invalid", field))
    for field in ("review_queued", "short_circuit", "emergency", "suppressed"):
        if not isinstance(raw.get(field, False), bool):
            problems.append(_problem("schema.invalid", field))
    if not _is_int(raw.get("model_calls", 0)) or raw.get("model_calls", 0) < 0:
        problems.append(_problem("schema.invalid", "model_calls"))
    plan = raw.get("plan")
    if plan is not None:
        _, plan_problems = validate_turn_plan(plan)
        problems += plan_problems
    results = raw.get("specialist_results") or []
    if not isinstance(results, list):
        problems.append(_problem("schema.invalid", "specialist_results"))
    else:
        for result in results:
            _, result_problems = validate_specialist_result(result, today=today)
            problems += result_problems
    outcome = raw.get("executed_outcome")
    if outcome is not None:
        _, outcome_problems = validate_executed_outcome(outcome)
        problems += outcome_problems
    last_outcome = raw.get("last_executed_outcome")
    if last_outcome is not None:
        _, last_problems = validate_executed_outcome(last_outcome)
        problems += last_problems
    bubble_plan = raw.get("bubble_plan")
    if bubble_plan is not None:
        _, bubble_problems = validate_bubble_plan(bubble_plan, allow_suppressed=True)
        problems += bubble_problems
    violations = raw.get("violations") or []
    if not isinstance(violations, list):
        problems.append(_problem("schema.invalid", "violations"))
    else:
        for violation in violations:
            if not isinstance(violation, dict) or set(violation) - VIOLATION_KEYS:
                problems.append(_problem("schema.invalid", "violation"))
                break
            if not isinstance(violation.get("hard", False), bool):
                problems.append(_problem("schema.invalid", "violation.hard"))
                break
    if problems:
        return None, problems
    return copy.deepcopy(raw), []


def apply_patch(draft, patch, version, reason_codes=None, today=None):
    """Apply a set/clear/add patch. Returns (draft, problems).

    A patch that does not change anything returns `patch.no_change` and does not
    bump the version. A stale version returns the original draft. The input is
    never mutated.
    """
    current, problems = validate_incident_draft(draft)
    if problems:
        return draft, problems
    if not _is_int(version):
        return draft, [_problem("schema.invalid", "version")]
    if version != current["version"]:
        return draft, ["patch.stale_version"]
    problems = _validate_patch_shape(patch)
    if problems:
        return draft, problems
    reasons = reason_codes or []
    if (patch.get("clear") or []) and (not reasons or not _string_list(reasons)
                                       or any(code not in CLEAR_REASONS for code in reasons)):
        return draft, ["patch.clear_without_reason"]

    updated = copy.deepcopy(current)
    changed = False

    for field, value in (patch.get("set") or {}).items():
        if value is None:
            continue
        if field == "description":
            text = _text(value, limit=None)
            if not text:
                if current.get("description"):
                    return draft, [_problem("patch.empty_value", "description")]
                continue
            if text != updated.get("description"):
                updated["description"] = text
                changed = True
        elif field == "category_id":
            if not _text(value):
                return draft, [_problem("patch.empty_value", "category_id")]
            if value != updated.get("category_id"):
                updated["category_id"] = value
                changed = True
        elif field == "category_candidates":
            if value != updated.get("category_candidates"):
                updated["category_candidates"] = copy.deepcopy(value)
                changed = True
        elif field == "severity":
            if value not in SEVERITIES:
                return draft, [_problem("schema.invalid", "severity")]
            if value != updated.get("severity"):
                updated["severity"] = value
                changed = True
        elif field == "location":
            for key, item in value.items():
                if item is None or item == "":
                    continue
                if key not in LOCATION_KEYS:
                    return draft, [_problem("patch.unknown_key", f"location.{key}")]
                if key == "provenance" and item not in PROVENANCE:
                    return draft, [_problem("schema.invalid", "location.provenance")]
                if key == "text" and not _text(item) and (current.get("location") or {}).get("text"):
                    return draft, [_problem("patch.empty_value", "location.text")]
                if (updated["location"].get(key) != item):
                    updated["location"][key] = item
                    changed = True

    for field, items in (patch.get("add") or {}).items():
        for item in items:
            if field == "attachments":
                if not isinstance(item, dict) or item.get("kind") not in ATTACHMENT_KINDS \
                        or not _text(item.get("ref")):
                    return draft, [_problem("schema.invalid", "attachment")]
                if any(existing.get("ref") == item.get("ref")
                       for existing in updated["attachments"]):
                    continue
            elif field == "evidence":
                if not isinstance(item, dict) or set(item) - EVIDENCE_KEYS:
                    return draft, [_problem("schema.invalid", "evidence")]
                marker = item.get("ref") or item.get("text")
                if marker and any((old.get("ref") or old.get("text")) == marker
                                  for old in updated["evidence"]):
                    continue
            elif field == "retracted":
                if not isinstance(item, dict) or set(item) - RETRACTED_KEYS \
                        or not _text(item.get("claim")):
                    return draft, [_problem("schema.invalid", "retracted")]
                if any(old.get("claim") == item.get("claim") for old in updated["retracted"]):
                    continue
            updated[field].append(copy.deepcopy(item))
            changed = True

    for field in patch.get("clear") or []:
        if field == "location":
            text = (updated.get("location") or {}).get("text") or ""
            if text and text.strip().lower() != LOCATION_UNKNOWN.lower():
                return draft, [_problem("patch.protected", "location")]
            if updated["location"] != empty_location():
                updated["location"] = empty_location()
                changed = True
        elif field == "category_id":
            if updated.get("category_id") is not None:
                updated["category_id"] = None
                changed = True
        elif field == "category_candidates":
            if updated.get("category_candidates"):
                updated["category_candidates"] = []
                changed = True
        elif field == "severity":
            if updated.get("severity") is not None:
                updated["severity"] = None
                changed = True

    if not changed:
        return draft, ["patch.no_change"]
    updated["version"] = current["version"] + 1
    _, problems = validate_incident_draft(updated)
    if problems:
        return draft, problems
    return updated, []


def set_policy_fields(draft, capture_state=None, routing_status=None, reason=None):
    """The only writer for the policy-owned fields. Used by policy and execute."""
    current, problems = validate_incident_draft(draft)
    if problems:
        return draft, problems
    if not reason:
        return draft, ["policy.reason_required"]
    if capture_state is not None and capture_state not in CAPTURE_STATES:
        return draft, [_problem("schema.invalid", "capture_state")]
    if routing_status is not None and routing_status not in ROUTING_STATUSES:
        return draft, [_problem("schema.invalid", "routing_status")]
    updated = copy.deepcopy(current)
    changed = False
    if capture_state is not None and capture_state != updated.get("capture_state"):
        updated["capture_state"] = capture_state
        changed = True
    if routing_status is not None and routing_status != updated.get("routing_status"):
        updated["routing_status"] = routing_status
        changed = True
    if not changed:
        return draft, ["patch.no_change"]
    updated["version"] = current["version"] + 1
    return updated, []

"""Graph shell nodes: hydrate, precheck, cheap, capture.

Step 6 has no decision model, no write, no writer and no delivery. The nodes only
prove the thread, the deterministic prechecks and the provisional capture draft.
"""

import re

import tools
import triage
from . import execution, policy, prompts
from .state import MAX_RECENT_MESSAGES, new_incident_draft, new_thread_state

SILENCE_WORDS = re.compile(
    r"^(thanks|thank you|cheers|ta|ok|okay|cool|got it|perfect|great|nice one)[\s!.,]*$",
    re.IGNORECASE,
)
GREETING_WORDS = re.compile(
    r"^(hi|hello|hey|hiya|good (morning|afternoon|evening))( there)?[\s!.,]*$",
    re.IGNORECASE,
)
# The same boundary as agents/safety.py, copied so the graph does not import the
# legacy orchestrator package.
THREAT = re.compile(
    r"\b(i('ll| will| am going to|'m going to|m gonna| gonna)\s+(kill|hurt|stab|shoot|attack)|"
    r"bomb (the|your)|burn (the|your) \w+( \w+)? down)\b",
    re.IGNORECASE,
)
URL = re.compile(r"https?://\S+", re.IGNORECASE)
MAPS = re.compile(r"maps\.apple\.com|google\.[a-z.]+/maps|maps\.app\.goo\.gl|goo\.gl/maps|geo:", re.IGNORECASE)
SPAM_URLS = 3
SPAM_CHARS = 3000


def wants_silence(text):
    return bool(text) and len(text) <= 25 and bool(SILENCE_WORDS.search(text))


def wants_greeting(text):
    return bool(text) and len(text) <= 25 and bool(GREETING_WORDS.search(text))


def danger(text):
    """Return emergency, threat, spam or None. The same order as the legacy guard."""
    text = text or ""
    if not text:
        return None
    if triage.EMERGENCY_WORDS.search(text):
        return "emergency"
    if THREAT.search(text):
        return "threat"
    if len(text) > SPAM_CHARS or len([url for url in URL.findall(text) if not MAPS.search(url)]) >= SPAM_URLS:
        return "spam"
    return None


def _inbound(state):
    return state.get("inbound") or {}


def _text(state):
    return (_inbound(state).get("text") or "").strip()


def make_nodes(deps):
    """Bind the dependencies once; every node is a plain callable."""

    def hydrate(state):
        inbound = _inbound(state)
        sender = inbound.get("sender") or ""
        thread_id = tools.reporter_ref(sender) or "h-anon"
        turn_id = state.get("turn_id") or inbound.get("message_guid") or ""
        base = new_thread_state(thread_id, turn_id, inbound)
        row = deps.threads.load(thread_id)
        if row:
            base.update({
                "active_incident_id": row.get("active_incident_id"),
                "incident_draft": row.get("incident_draft") or new_incident_draft(),
                "pending_question": row.get("pending_question"),
                "last_claims_sent": row.get("last_claims") or [],
            })
        if row and row.get("last_turn_id") == turn_id:
            base.update({
                "suppressed": True,
                "short_circuit": False,
                "emergency": False,
                "recent_messages": list(state.get("recent_messages") or []),
            })
            return base
        entry = {
            "role": "resident",
            "text": inbound.get("text") or "",
            "at": deps.now().isoformat(timespec="seconds"),
        }
        messages = list(state.get("recent_messages") or [])
        messages = messages + [entry] if messages else [entry]
        base.update({
            "recent_messages": messages[-MAX_RECENT_MESSAGES:],
            "suppressed": False,
            "short_circuit": False,
            "emergency": False,
        })
        return base

    def precheck(state):
        inbound = _inbound(state)
        text = _text(state)
        if not text and not (inbound.get("photo_ref") or inbound.get("image_ref")
                             or inbound.get("card")):
            return {"suppressed": True, "emergency": False, "short_circuit": False}
        kind = danger(text)
        if kind == "emergency":
            return {"emergency": True, "short_circuit": True}
        if kind in ("threat", "spam"):
            return {"emergency": False, "short_circuit": True}
        return {"emergency": False, "short_circuit": False}

    def cheap(state):
        text = _text(state)
        if wants_silence(text):
            return {"suppressed": True}
        if wants_greeting(text):
            return {"short_circuit": True}
        return {}

    def capture(state):
        inbound = _inbound(state)
        text = _text(state)
        ref = inbound.get("photo_ref") or inbound.get("image_ref")
        previous = state.get("incident_draft") or {}
        previous_text = (previous.get("description") or "").strip()
        place = prompts.extract_location(text)
        detail_only = bool(previous_text) and (
            prompts.is_detail(text, state)
            or (not text and (ref or inbound.get("card")))
            or prompts.is_challenge(text)
            or prompts.is_question(text)
        )
        if detail_only:
            draft = dict(previous)
            draft["version"] = int(draft.get("version") or 0) + 1
            if place:
                draft["location"] = {"text": place, "street": place,
                                     "area": None, "postcode": None,
                                     "provenance": "text", "ambiguous": False}
        else:
            draft = new_incident_draft(text)
            if place:
                draft["location"] = {"text": place, "street": place,
                                     "area": None, "postcode": None,
                                     "provenance": "text", "ambiguous": False}
        features = None
        if isinstance(ref, (tuple, list)) and ref:
            guid = str(ref[0])
            mime = str(ref[1]) if len(ref) > 1 and ref[1] else "image/jpeg"
            ref = guid if guid.startswith("guid:") else f"guid:{guid}"
            features = {"mime": mime}
        if ref:
            existing = list(draft.get("attachments") or [])
            if not any(item.get("ref") == str(ref) for item in existing):
                attachment = {"kind": "photo", "ref": str(ref)}
                if features:
                    attachment["features"] = features
                existing.append(attachment)
            draft["attachments"] = existing
        card = inbound.get("card")
        if card:
            try:
                from agents.location_agent import LocationAgent
                shared = LocationAgent().shared_place("", card)
            except Exception as error:  # noqa: BLE001 - a card must not break the turn
                print(f"[card] could not read the shared location: {error}")
                shared = None
            if shared and shared.get("street_name"):
                draft["location"] = {
                    "text": shared["street_name"],
                    "street": shared["street_name"],
                    "area": shared.get("area"),
                    "postcode": shared.get("postcode"),
                    "provenance": "pin",
                    "ambiguous": False,
                }
        return {"incident_draft": draft, "candidate_services": []}

    def decide(state):
        repairing = state.get("repair_count", 0) >= 1
        calls = 0
        degraded = []
        plan = None
        if not repairing and deps.llm is not None and hasattr(deps.llm, "chat"):
            try:
                reply, mode = deps.llm.chat(
                    prompts.SYSTEM, prompts.brief(state, deps),
                    max_tokens=700, temperature=0.1, timeout=8, purpose="decide")
                calls = 1
                if mode == "model":
                    plan, problems = prompts.parse(reply)
                    if plan is None:
                        degraded.append("plan_invalid")
                else:
                    degraded.append("llm_offline")
            except Exception as error:  # noqa: BLE001 - a model failure must not lose the report
                calls = 1
                degraded.append("llm_error")
                print(f"[decide] model failed: {error}")
        if plan is None:
            plan = (prompts.repair_plan(state, deps) if repairing
                    else prompts.deterministic_plan(state, deps))
        return {"plan": plan, "violations": [],
                "model_calls": state.get("model_calls", 0) + calls,
                "degraded": list(dict.fromkeys((state.get("degraded") or []) + degraded))}

    def validate(state):
        found = policy.check(state, execution.context(deps, state))
        merged = (state.get("violations") or []) + found
        unique = []
        seen = set()
        for item in merged:
            key = (item.get("code"), item.get("field"))
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return {"violations": unique}

    def repair(state):
        return {"repair_count": min(2, state.get("repair_count", 0) + 1)}

    def fallback(state):
        return {"plan": prompts.fallback_plan(state, deps), "violations": []}

    def execute(state):
        return execution.execute(state, deps)

    def compose(state):
        return execution.compose(state, deps)

    def lint(state):
        return execution.lint(state, deps)

    def enqueue(state):
        return execution.enqueue(state, deps)

    return {"hydrate": hydrate, "precheck": precheck, "cheap": cheap, "capture": capture,
            "decide": decide, "validate": validate, "repair": repair, "fallback": fallback,
            "execute": execute, "compose": compose, "lint": lint, "enqueue": enqueue}


def route_precheck(state):
    return "end" if state.get("suppressed") or state.get("emergency") else "cheap"


def route_cheap(state):
    return "end" if state.get("suppressed") or state.get("short_circuit") else "capture"


def route_validate(state):
    return policy.decide(state.get("violations") or [], state.get("repair_count", 0))

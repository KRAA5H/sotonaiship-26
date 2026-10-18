"""Graph shell nodes: hydrate, precheck, cheap, capture.

Step 6 has no decision model, no write, no writer and no delivery. The nodes only
prove the thread, the deterministic prechecks and the provisional capture draft.
"""

import re

import tools
import triage
from .state import MAX_RECENT_MESSAGES, new_incident_draft

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
    if len(text) > SPAM_CHARS or len(URL.findall(text)) >= SPAM_URLS:
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
        row = deps.threads.load(thread_id)
        if row and row.get("last_turn_id") == turn_id:
            return {"thread_id": thread_id, "turn_id": turn_id,
                    "inbound": inbound, "suppressed": True,
                    "short_circuit": False, "emergency": False}
        messages = list(state.get("recent_messages") or [])
        messages.append({
            "role": "resident",
            "text": inbound.get("text") or "",
            "at": deps.now().isoformat(timespec="seconds"),
        })
        return {
            "thread_id": thread_id,
            "turn_id": turn_id,
            "inbound": inbound,
            "active_incident_id": row.get("active_incident_id") if row else None,
            "incident_draft": (row.get("incident_draft") if row else None)
            or new_incident_draft(),
            "pending_question": row.get("pending_question") if row else None,
            "last_claims_sent": (row.get("last_claims") if row else None) or [],
            "recent_messages": messages[-MAX_RECENT_MESSAGES:],
            "suppressed": False,
            "short_circuit": False,
            "emergency": False,
        }

    def precheck(state):
        inbound = _inbound(state)
        text = _text(state)
        if not text and not inbound.get("photo_ref"):
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
        draft = new_incident_draft(_text(state))
        ref = inbound.get("photo_ref")
        if ref:
            draft["attachments"] = [{"kind": "photo", "ref": str(ref)}]
        return {"incident_draft": draft, "candidate_services": []}

    return {"hydrate": hydrate, "precheck": precheck, "cheap": cheap, "capture": capture}


def route_precheck(state):
    return "end" if state.get("suppressed") or state.get("emergency") else "cheap"


def route_cheap(state):
    return "end" if state.get("suppressed") or state.get("short_circuit") else "capture"

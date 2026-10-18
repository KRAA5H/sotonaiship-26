"""Graph shell nodes: hydrate, precheck, cheap, capture.

Step 6 has no decision model, no write, no writer and no delivery. The nodes only
prove the thread, the deterministic prechecks and the provisional capture draft.
"""

import re

import tools
import triage
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
        if not text and not (inbound.get("photo_ref") or inbound.get("image_ref")):
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
        ref = inbound.get("photo_ref") or inbound.get("image_ref")
        if isinstance(ref, (tuple, list)) and ref:
            guid = str(ref[0])
            ref = guid if guid.startswith("guid:") else f"guid:{guid}"
        if ref:
            draft["attachments"] = [{"kind": "photo", "ref": str(ref)}]
        return {"incident_draft": draft, "candidate_services": []}

    return {"hydrate": hydrate, "precheck": precheck, "cheap": cheap, "capture": capture}


def route_precheck(state):
    return "end" if state.get("suppressed") or state.get("emergency") else "cheap"


def route_cheap(state):
    return "end" if state.get("suppressed") or state.get("short_circuit") else "capture"

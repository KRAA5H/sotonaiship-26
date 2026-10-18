"""The model writes the reply. The runtime owns the link and the truth checks.

The writer sees the resident's message and what actually happened, never the
report plan and never the link. If its JSON is unusable, the raw model text is
used as one bubble rather than a canned template. The only fixed resident copy
left is the 999 instruction.
"""

import json
import re

from . import schemas

SYSTEM = """You are Kerbside, a Southampton council text assistant writing to a
resident on iMessage. Write the reply as 1 to 3 short bubbles, like a real person
texting from their phone. Match the resident's register. If they write formally or
politely, with capitals and full sentences, reply in calm professional British
English, properly capitalised, no slang, no corporate phrases. If they text casually,
reply casually in lower case, lightly gen z but never cringe. No emojis, no markdown,
no em dashes, no URLs. Each bubble is one or two sentences and under 300 characters.
Ask at most one question. The report is saved on the server here, never on the
resident's phone, and it is a report, not a draft.

You are given the resident's message and the executed outcome. Say only what the
outcome says. Never invent a category, team, crew, timescale, phone number, fact or
council receipt. If a report was saved locally, say it has not gone to the council
yet. If a report was not saved, do not imply it was. If a question was answered,
use the supplied facts. If a follow-up question is needed, ask it in your own words.
Do not write the report link; the system adds it. Return only JSON:
{"bubbles": ["first bubble", "second bubble"]}"""


def _register(text):
    text = (text or "").strip()
    lowered = text.lower()
    if re.search(r"\b(yo|sup|wassup|wht|hv|bro|mate|cheers|lol|snm|g)\b", lowered):
        return "casual"
    if re.search(r"\b(hello|good morning|good afternoon|please|could you|i have|"
                 r"i would|thank you|kindly)\b", lowered):
        return "formal"
    if text and text[0].isupper() and len(text.split()) >= 5:
        return "formal"
    return "casual"


def _brief(state, outcome):
    draft = state.get("incident_draft") or {}
    plan = state.get("plan") or {}
    resident = (state.get("inbound") or {}).get("text") or ""
    return json.dumps({
        "resident_message": resident,
        "register": _register(resident),
        "recent": [item.get("text") for item in (state.get("recent_messages") or [])[-6:]],
        "draft": {
            "category_id": draft.get("category_id"),
            "description": draft.get("description"),
            "location": (draft.get("location") or {}).get("text"),
        },
        "action": outcome.get("action"),
        "saved": outcome.get("saved"),
        "duplicate_of": outcome.get("duplicate_of"),
        "missing": outcome.get("missing") or [],
        "facts": outcome.get("facts") or [],
        "status": {key: (outcome.get("status") or {}).get(key)
                   for key in ("status_text", "category", "location", "description")}
                  if outcome.get("status") else None,
        "destination": outcome.get("destination"),
        "refused_reason": outcome.get("refused_reason"),
        "question": (state.get("pending_question") or {}).get("text"),
        "challenge": bool(plan.get("retracted_claims"))
                     or plan.get("dialogue_act") == "challenge_previous_claim",
        "photo_coming": "photo_announcement" in (plan.get("reason_codes") or []),
        "last_claims": state.get("last_claims_sent") or [],
    }, ensure_ascii=False, separators=(",", ":"))


def _lowercase(text):
    text = (text or "").strip()
    if not text:
        return text
    text = text[0].lower() + text[1:]
    return re.sub(r"([.!?]\s+)([A-Z])",
                  lambda match: match.group(1) + match.group(2).lower(), text)


def _parse(raw, casual=True):
    body = (raw or "").strip()
    if body.startswith("```"):
        body = re.sub(r"^```(?:json)?\s*", "", body)
        body = re.sub(r"\s*```$", "", body)
    start, end = body.find("{"), body.rfind("}")
    if start >= 0 and end > start:
        body = body[start:end + 1]
    try:
        data = json.loads(body)
    except (ValueError, TypeError):
        return None
    bubbles = data.get("bubbles") if isinstance(data, dict) else None
    if not isinstance(bubbles, list):
        return None
    clean = []
    for item in bubbles:
        text = item.get("text") if isinstance(item, dict) else item
        if isinstance(text, str) and text.strip():
            value = " ".join(text.split())
            clean.append(_lowercase(value) if casual else value)
    return clean or None


_BANNED = re.compile(r"\b(on your phone|your phone|your device|draft)\b", re.I)


def _safe(texts, outcome, ctx):
    joined = " ".join(texts)
    if _BANNED.search(joined):
        return None
    plan = {
        "bubbles": [{"purpose": "question" if "?" in text else "action", "text": text}
                    for text in texts],
        "url": None, "source_url": None, "suppressed": False,
    }
    checked, problems = schemas.validate_bubble_plan(plan)
    if problems or not checked:
        return None
    from . import policy
    claims = policy.check_bubbles(texts, outcome, ctx)
    if claims:
        return None
    return checked


def write(state, deps, outcome, ctx):
    """Return a BubblePlan without links, or None when the model is unavailable."""
    if deps.llm is None or not hasattr(deps.llm, "chat"):
        return None
    brief = _brief(state, outcome)
    last_problem = ""
    for attempt in range(2):
        prompt = brief if not last_problem else f"{brief}\n\nYour last reply failed: {last_problem}. Return corrected JSON."
        try:
            reply, mode = deps.llm.chat(SYSTEM, prompt, max_tokens=500,
                                        temperature=0.8, timeout=8, purpose="writer")
        except Exception as error:  # noqa: BLE001 - a writer failure must not crash the turn
            print(f"[writer] model failed: {error}")
            return None
        if mode != "model":
            return None
        texts = _parse(reply, casual=_register((state.get("inbound") or {}).get("text") or "") == "casual")
        if texts:
            checked = _safe(texts, outcome, ctx)
            if checked:
                return checked
            last_problem = "one or more bubbles contained a URL, markdown, an unsupported claim, or more than three bubbles"
        else:
            # A plain sentence is still the model speaking. One short bubble is safer
            # than replacing its voice with a template.
            plain = " ".join((reply or "").split())[:300]
            if _register((state.get("inbound") or {}).get("text") or "") == "casual":
                plain = _lowercase(plain)
            if plain.startswith(("{", "[")):
                plain = ""
            if plain and not re.search(r"https?://|www\.", plain, re.I):
                checked = _safe([plain], outcome, ctx)
                if checked:
                    return checked
            last_problem = "the reply was not the requested JSON object"
    return None

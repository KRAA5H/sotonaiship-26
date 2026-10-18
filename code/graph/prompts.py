"""Decision prompt, deterministic plans and the captured fallback.

The model proposes one plan. Nothing it says is trusted until the schema and the
policy have checked it. When the model is absent or wrong, the deterministic
plans below still keep the incident and still act.
"""

import json
import re
from functools import lru_cache
from pathlib import Path

from . import evidence, schemas

PLAYBOOK_DIR = Path(__file__).resolve().parents[1] / "services" / "playbooks"

SYSTEM = """You are Kerbside, a Southampton council text assistant. Read one resident
message and the incident draft, then return ONE JSON object and nothing else.

Actions: log, ask, answer, escalate.
- log: keep a physical problem. A physical problem is never dropped because the category
  is uncertain. If no category fits, use "unclear_other".
- ask: ask ONE question for a missing field. Never ask for a field that is already known.
- answer: answer a question using only the checked facts supplied. Never invent a fact,
  a team, a number, a timescale or council receipt.
- escalate: point to an official service only when the playbook says not_council or the
  facts do not settle a question.

Capture-first: a report about a real-world problem gets action log, even when the
category is unclear or the model's best category is info_only. Use "unclear_other".
If the only missing field is the location, still choose log: the reply asks for the
location after saving. Use ask only when there is no description or photo at all.
Never choose not_council for a physical problem. Never say the council has the report:
a local save has not gone to the council yet.

JSON shape:
{"dialogue_act": "new_report|detail|correction|challenge_previous_claim|question|status|greeting|other",
 "action": "log|ask|answer|escalate",
 "incident_patch": {"set": {"description": "...", "category_id": "pothole",
   "location": {"text": "12 Alma Road", "street": "Alma Road", "provenance": "text"}},
   "clear": [...], "add": {...}},
 "service_candidates": ["category_id"],
 "specialist_request": null,
 "clarification": {"field": "location|description|address|detail|photo", "reason": "..."} or null,
 "fact_request": {"question": "...", "category_id": "..."} or null,
 "escalation": {"kind": "...", "destination": "..."} or null,
 "retracted_claims": [],
 "reason_codes": [],
 "profile_patch": {"name": "...", "address": "...", "phone": "...", "style": "casual|formal"},
 "task_request": {"kind": "permit|council_tax|bins", "fields": {"name": "...", "address": "...", "vehicle": "..."}}}

You are the conversation director. Read the whole conversation, not one message.
A short reply after an agent question is an answer to that question: name, address,
phone, location or photo. A greeting, thanks, insult, "what do you mean" or confusion
is not a report. A status question reads the active report. Never save a greeting,
thanks, name, address, phone, confusion or a message with no concrete problem. Saving
"hello", "krish" or "wdym" is forbidden. Ask exactly one question, never two. Fill profile_patch only
when the conversation establishes it; do not ask for all the profile fields at once.
Infer the resident's style and put it in profile_patch.style when it is clear.

For a permit or council tax task, use task_request. Dialogue_act is other and action is
ask or answer. Permit requires name, address and vehicle. Ask exactly one missing field
at a time. When all fields are present, return the task_request with action answer. The backend prepares a case and gives a reference.
Never claim the council has accepted it. A task is not a report.

Allowed pairs: new_report, detail and correction -> log or ask; question -> answer or escalate;
status and challenge_previous_claim -> answer; greeting and other -> answer, ask or escalate.
Escalation kinds: emergency_999, national_highways, utility, council_complaints,
council_out_of_hours, adult_social_care, council_finder, council_form.
incident_patch may be {} (no change). To clear a field, include reason_codes.
Clearable fields: category_id, category_candidates, severity, location.
Use no markdown and no extra keys. Keep one question at most."""

_KEYWORDS = (
    ("not_council_trunk_road", ("motorway", "a33", "a36", "m27", "m3", "trunk road")),
    ("noise_nuisance", ("noisy neighbour", "noisy neighbor", "neighbour noise",
                        "loud music", "barking dog", "noise from next door",
                        "noise nuisance")),
    ("not_council_utility", ("power cut", "electricity", "water leak", "gas leak")),
    ("pothole", ("pothole", "hole in the road", "road surface", "crater", "sunken drain")),
    ("fly_tipping", ("fly tip", "fly-tip", "dumped rubbish", "dumped waste", "mattress",
                     "fridge", "sofa dumped", "rubbish dumped")),
    ("graffiti_flyposting", ("graffiti", "flypost", "fly poster", "fly-poster")),
    ("dog_fouling", ("dog foul", "dog poo", "dog mess")),
    ("glass_spillage_hazard", ("broken glass", "glass on", "smashed bottle")),
    ("dead_animal", ("dead animal", "dead fox", "dead bird", "dead cat", "dead dog")),
    ("abandoned_vehicle", ("abandoned car", "abandoned van", "untaxed car")),
    ("illegal_parking", ("parked on", "double parked", "blocking my drive", "illegal parking")),
    ("missed_bin", ("missed bin", "bin not collected", "bins not collected",
                    "bin wasn't collected", "bin was not collected")),
    ("lost_damaged_bin", ("missing bin", "broken bin", "damaged bin", "bin lid")),
    ("litter_street_cleaning", ("litter", "street cleaning", "street needs sweeping")),
    ("council_housing_repair", ("housing repair", "council house", "leak in my flat", "damp")),
    ("flooding_severe_weather", ("flood", "flooding", "storm")),
)


_REPORT_WORDS = re.compile(
    r"\b(tree|fallen|blocking|blocked|broken|dumped|leak|spill|fly.?tip|graffiti|"
    r"litter|pothole|hole|crater|flood|noise|smell|damp|damaged|missing|abandoned|"
    r"parked|fouling|glass|rubbish|bin)\b", re.I)
_QUESTION_START = re.compile(
    r"^(what|how|where|when|why|who|can|could|do|does|is|are|will|should|may)\b", re.I)
_CHALLENGE = re.compile(
    r"(what has that got to do|that'?s wrong|that is wrong|you said|"
    r"wasn'?t|was not|nothing to do with|why did you say|got that wrong)", re.I)
_TRUNK_TEXT = re.compile(r"\b(A3[36]|M27|M3|motorway|trunk road)\b", re.I)
_OUTSIDE_TEXT = re.compile(r"\b(winchester|eastleigh|fareham|portsmouth|gosport|romsey|outside southampton)\b(?!\s+(?:road|street|lane|avenue|close|drive|way|crescent|gardens|hill|park|terrace|place|grove|court|walk|mews|rise|row)\b)", re.I)
_HANDOFF_TEXT = re.compile(
    r"\b(noisy (neighbour|neighbor)|neighbour(s)? (noise|making noise)|loud music|"
    r"barking dog|noise from (next door|the neighbours?)|noise nuisance)\b", re.I)
_GREETING_TEXT = re.compile(
    r"^(hi|hello|hey|hiya|yo+|sup|wassup|wagwan|wag1|what'?s up|"
    r"good (morning|afternoon|evening)|morning|evening)( there)?[\s!.,]*$", re.I)
_PLACE_HINT = re.compile(
    r"\b(near|by|at|on|outside|opposite|next to|behind|in front of|corner|"
    r"junction|postcode|street|road|lane|avenue|close|drive|way|crescent|"
    r"gardens|hill|park|terrace|place|grove|court|walk|mews|rise|row)\b", re.I)
_STATUS_TEXT = re.compile(
    r"\b(any update|update on (my|the) report|what'?s (the )?status|status of (my|the) report|"
    r"has (it|my report) been|is it fixed|still open|any progress)\b|"
    r"\b(what|wht)\b.*\b(logged|report|draft)\b", re.I)
_UTILITY_TEXT = re.compile(r"\b(power cut|electricity|water leak|gas leak)\b", re.I)
_PROBLEM_EXTRA = re.compile(
    r"\b(power cut|dead (fox|cat|dog|bird|animal)|parking|wasp|nest|pest|vermin|"
    r"damp|mould|sewage|drain|infestation|smell|odour|noise)\b", re.I)
_PHOTO_ANNOUNCEMENT = re.compile(
    r"\b(send|sending|take|taking|got)\s+(you\s+)?(a\s+)?(photo|pic|picture)|"
    r"photo\s+(of|coming)|i'?ll\s+send|ill\s+send|i\s+will\s+send", re.I)
_POSTCODE = re.compile(r"\bSO\d{1,2}\s?\d[A-Z]{2}\b", re.I)
_SUFFIX = r"(?:Road|Street|Lane|Avenue|Close|Drive|Way|Crescent|Gardens|Hill|Park|Terrace|Place|Grove|Court|Walk|Mews|Rise|Row)"
_PREP_STREET = re.compile(r"\b(?:on|at|outside|near|by|in)\s+([A-Z][\w']*(?:\s+[A-Z][\w']*){0,4}\s+" + _SUFFIX + r")\b", re.I)
_ANY_STREET = re.compile(r"\b([A-Z][\w']*(?:\s+[A-Z][\w']*){0,4}\s+" + _SUFFIX + r")\b", re.I)
_SHORT_STREET = re.compile(r"^[A-Za-z0-9' .-]{2,40}\b" + _SUFFIX + r"[\s.,!]*$", re.I)


@lru_cache(maxsize=None)
def playbook(category):
    """Load one generated playbook. Unknown or unsafe ids get an empty book."""
    if not isinstance(category, str) or "/" in category or "\\" in category:
        return {}
    path = PLAYBOOK_DIR / f"{category}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def candidates_for(text, index=None):
    """Ordered category guesses. `unclear_other` is always the fallback, never a veto."""
    lowered = (text or "").lower()
    found = []
    for category, words in _KEYWORDS:
        if any(word in lowered for word in words) and category not in found:
            found.append(category)
    known = set((index or {}).get("categories") or {})
    found = [item for item in found if not known or item in known]
    if "unclear_other" in known:
        found.append("unclear_other")
    return found or ["unclear_other"]


def extract_location(text):
    """A place we can act on. A district name alone is not enough."""
    text = (text or "").strip()
    if not text:
        return None
    postcode = _POSTCODE.search(text)
    if postcode:
        return postcode.group(0).upper()
    match = _PREP_STREET.search(text)
    if not match:
        match = _ANY_STREET.search(text)
    if match and match.group(1).strip().lower() in {
            "the road", "road", "the street", "street", "the pavement"}:
        return None
    if match and not _REPORT_WORDS.search(match.group(1)):
        place = match.group(1).strip(" .,")
        for separator in (" at ", " on ", " near ", " outside ", " in "):
            if separator in place.lower():
                place = re.split(separator, place, flags=re.I)[-1].strip()
        place = re.sub(r"^(the|a|an)\s+", "", place, flags=re.I).strip(" .,")
        if place and place.islower():
            place = place.title()
        return place or None
    if _SHORT_STREET.match(text) and not _REPORT_WORDS.search(text):
        place = text.strip(" .,")
        return place.title() if place.islower() else place
    return None


def is_question(text):
    text = (text or "").strip()
    return bool(text) and (text.endswith("?") or bool(_QUESTION_START.match(text)))


def is_challenge(text):
    return bool(_CHALLENGE.search(text or ""))


def hard_route(text):
    """The routes the council rulebook forbids us to save, regardless of model."""
    text = text or ""
    if _TRUNK_TEXT.search(text):
        return "not_council_trunk_road"
    if _OUTSIDE_TEXT.search(text):
        return "outside_southampton"
    if _UTILITY_TEXT.search(text):
        return "not_council_utility"
    if _HANDOFF_TEXT.search(text):
        return "noise_nuisance"
    return None


def is_greeting(text):
    text = (text or "").strip()
    return bool(text) and len(text) <= 25 and bool(_GREETING_TEXT.search(text))


def is_status(text):
    return bool(_STATUS_TEXT.search(text or ""))


def is_photo_announcement(text):
    return bool(_PHOTO_ANNOUNCEMENT.search(text or ""))


_STOPWORDS = {"a", "an", "and", "at", "by", "for", "from", "here", "in", "is",
              "it", "its", "near", "of", "on", "or", "that", "the", "there", "this",
              "to", "was", "with"}


def _content_words(text):
    return [word.lower() for word in re.findall(r"[A-Za-z']+", text or "")
            if word.lower() not in _STOPWORDS]


_NAME_EXPLICIT = re.compile(
    r"\b(?:my name is|my name's|call me)\s+([A-Za-z][A-Za-z' -]{1,30})", re.I)
_NAME_SELF = re.compile(
    r"\b(?:i am|i'm|im)\s+(?!at\b|in\b|on\b|reporting\b|not\b|so\b|just\b|going\b|"
    r"looking\b|having\b|a\b|an\b|the\b)([A-Za-z][A-Za-z' -]{1,30})", re.I)
_ADDRESS = re.compile(
    r"\b(?:my address is|i live at|i live in|i'm at|im at|address:)\s+(.{3,100})", re.I)
_PHONE = re.compile(
    r"(\+44\s?\d{2,4}\s?\d{3,4}\s?\d{3,4}|\b0\d{3,4}\s?\d{3,4}\s?\d{3,4}\b)")


def extract_profile(text, last_claims=None):
    """The small profile: preferred name, address and phone, when offered."""
    text = " ".join((text or "").split())
    found = {}
    name = _NAME_EXPLICIT.search(text) or _NAME_SELF.search(text)
    if name:
        candidate = name.group(1).strip(" .,!?")
        if 1 <= len(candidate.split()) <= 4:
            found["name"] = candidate.title()
    elif last_claims and any(word in " ".join(last_claims).lower()
                             for word in ("call you", "your name")):
        words = text.strip(" .,!?").split()
        if 1 <= len(words) <= 3 and not _REPORT_WORDS.search(text):
            found["name"] = " ".join(words).title()
    address = _ADDRESS.search(text)
    if address:
        found["address"] = address.group(1).strip(" .,!?")
    elif last_claims and any("address" in claim.lower() for claim in last_claims):
        if 2 <= len(text.split()) <= 10 and not _REPORT_WORDS.search(text):
            found["address"] = text.strip(" .,!?")
    phone = _PHONE.search(text)
    if phone:
        found["phone"] = phone.group(1).strip()
    elif last_claims and any("phone" in claim.lower() for claim in last_claims):
        phone = _PHONE.search(text)
        if phone:
            found["phone"] = phone.group(1).strip()
    return found


def is_detail(text, state):
    """A message that adds to the open incident rather than starting a new one.

    Only a bare place, a pending location reply, a photo or "still there" counts.
    A second problem with its own noun is a new incident, never an overwrite.
    """
    draft = state.get("incident_draft") or {}
    if not state.get("active_incident_id") or not draft.get("description"):
        return False
    text = (text or "").strip()
    if is_greeting(text) or is_challenge(text) or is_question(text):
        return False
    if is_photo_announcement(text):
        return True
    if not text:
        return bool(draft.get("attachments")) or bool(state.get("pending_question"))
    if text.lower() in ("it is still there", "still there", "it's still there", "same problem"):
        return True
    if hard_route(text) or _PROBLEM_EXTRA.search(text) or _REPORT_WORDS.search(text):
        return False
    place = extract_location(text)
    if place:
        residual = re.sub(re.escape(place), " ", text, flags=re.I)
        return not _content_words(residual)
    pending = state.get("pending_question") or {}
    if pending.get("field") in ("location", "detail"):
        return bool(_PLACE_HINT.search(text))
    return False


def _reportish(text, category):
    if category != "unclear_other":
        return True
    return bool(_REPORT_WORDS.search(text or ""))


def likely_report(text, state=None):
    """True when the message looks like a real-world problem, not a greeting or query."""
    text = (text or "").strip()
    inbound = (state or {}).get("inbound") or {}
    if not text:
        return bool(inbound.get("photo_ref") or inbound.get("image_ref")
                    or inbound.get("card"))
    if hard_route(text) or _REPORT_WORDS.search(text) or _PROBLEM_EXTRA.search(text):
        return True
    guesses = candidates_for(text)
    if guesses and guesses[0] != "unclear_other":
        return True
    if extract_location(text):
        return True
    return bool(inbound.get("photo_ref") or inbound.get("image_ref") or inbound.get("card"))


def _plan(dialogue_act, action, candidates, patch=None, clarification=None,
          fact_request=None, escalation=None, retracted=None, reasons=None):
    return {
        "dialogue_act": dialogue_act,
        "action": action,
        "incident_patch": patch or {},
        "service_candidates": candidates or [],
        "specialist_request": None,
        "clarification": clarification,
        "fact_request": fact_request,
        "escalation": escalation,
        "retracted_claims": retracted or [],
        "reason_codes": reasons or [],
    }


def _location_patch(place):
    if not place:
        return {}
    return {"set": {"location": {"text": place, "street": place, "provenance": "text"}}}


def likely_duplicate(text, state):
    """A detail about the open incident is not a new report."""
    draft = state.get("incident_draft") or {}
    if not state.get("active_incident_id") or not draft.get("description"):
        return False
    if _CHALLENGE.search(text or ""):
        return False
    if is_challenge(text):
        return False
    if _REPORT_WORDS.search(text or "") and not _SHORT_STREET.match(text or ""):
        # A new problem word can still be detail ("it is still there"), so only
        # treat a different category word as a new incident.
        current = draft.get("category_id") or ""
        guesses = candidates_for(text, None)
        return bool(guesses and guesses[0] in ("unclear_other", current))
    return True


def deterministic_plan(state, deps):
    """The plan we trust when no model answered, and the floor under every repair."""
    inbound = state.get("inbound") or {}
    text = (inbound.get("text") or "").strip()
    draft = state.get("incident_draft") or {}
    index = deps.playbooks or {}
    categories = index.get("categories") or {}
    guesses = candidates_for(text, index)
    category = (draft.get("category_id") or guesses[0] or "unclear_other")
    place = extract_location(text)
    patch = _location_patch(place)
    never = set(index.get("never_saved") or ())
    handoff = set(index.get("handoff_categories") or ())
    info_only = {key for key, value in categories.items() if value == "info_only"}

    if is_challenge(text) and state.get("last_claims_sent"):
        wrong = "flooding" if "flooding" in text.lower() else None
        return _plan("other", "answer", [category],
                     fact_request={"question": text, "category_id": "general"},
                     retracted=[wrong] if wrong else [],
                     reasons=["challenge"])

    hard = hard_route(text)
    if hard:
        if hard in handoff:
            return _handoff_plan(index, hard)
        return _escalation_plan(index, hard)

    if is_photo_announcement(text):
        return _plan("detail", "log", [category], reasons=["photo_announcement"])

    if not text and (draft.get("attachments") or inbound.get("card")):
        return _plan("detail", "log", [category], reasons=["photo_detail"])

    if is_detail(text, state):
        return _plan("detail", "log", [category], patch=patch, reasons=["detail"])

    if is_status(text):
        if state.get("active_incident_id"):
            return _plan("status", "answer", [category],
                         fact_request={"question": text,
                                       "category_id": category if category in categories else "general"},
                         reasons=["status"])
        return _plan("other", "ask", [category],
                     clarification={"field": "description",
                                    "reason": "Nothing is logged yet. What's the problem and where?"},
                     reasons=["no_report"])

    if is_question(text):
        fact_category = category if category != "unclear_other" else "general"
        return _plan("question", "answer", [category],
                     fact_request={"question": text, "category_id": fact_category})

    if category in never or categories.get(category) == "not_council":
        return _escalation_plan(index, category)

    if category in handoff:
        form = playbook(category).get("form_url")
        if form:
            return _plan("other", "escalate", [category],
                         escalation={"kind": "council_form", "destination": form},
                         reasons=["handoff"])

    if category in info_only:
        category = "unclear_other"

    if category == "unclear_other" and not _reportish(text, category):
        return _plan("other", "ask", [category],
                     clarification={"field": "description",
                                    "reason": "Tell me what the problem is."})

    return _plan("new_report", "log", [category], patch=patch, reasons=["decided"])


def _escalation_plan(index, category):
    book = playbook(category)
    redirect = book.get("redirect_to") or ""
    guidance = (index.get("guidance") or {}).get(redirect) or {}
    destination = guidance.get("url") or guidance.get("contact")
    kind = "council_finder"
    if redirect == "national_highways":
        kind = "national_highways"
    elif redirect == "council_out_of_hours":
        kind = "council_out_of_hours"
    elif category == "not_council_utility":
        kind = "utility"
        facts = book.get("facts") or []
        destination = destination or (facts[0].get("url") if facts else None) \
            or ((index.get("guidance") or {}).get("find_your_council") or {}).get("url")
    if not destination:
        destination = ((index.get("guidance") or {}).get("find_your_council") or {}).get("url")
    return _plan("other", "escalate", [category],
                 escalation={"kind": kind, "destination": destination},
                 reasons=["not_council"])


def _handoff_plan(index, category):
    book = playbook(category)
    form = book.get("form_url")
    if not form:
        return _escalation_plan(index, category)
    return _plan("other", "escalate", [category],
                 escalation={"kind": "council_form", "destination": form},
                 reasons=["handoff"])


def _proposed_category(state):
    draft = state.get("incident_draft") or {}
    plan = state.get("plan") or {}
    patch = ((plan.get("incident_patch") or {}).get("set") or {})
    candidates = plan.get("service_candidates") or state.get("candidate_services") or []
    return draft.get("category_id") or patch.get("category_id") \
        or (candidates[0] if candidates else None)


def repair_plan(state, deps):
    """One deterministic correction, never another model call."""
    draft = state.get("incident_draft") or {}
    violations = state.get("violations") or []
    codes = {item.get("code") for item in violations}
    if "retraction.missing" in codes:
        return _plan("other", "ask", [draft.get("category_id") or "unclear_other"],
                     clarification={"field": "location", "reason": "Where is it?"},
                     reasons=["challenge_repair"])
    if "ask.known_field" in codes or "policy.question_repeated" in codes:
        target = "description" if not ((draft.get("description") or "").strip()
                                       or draft.get("attachments")) else "location"
        return _plan("other", "ask", [draft.get("category_id") or "unclear_other"],
                     clarification={"field": target, "reason": "Tell me a bit more."})
    category = _proposed_category(state)
    hard = hard_route(((state.get("inbound") or {}).get("text") or ""))
    if hard:
        index = deps.playbooks or {}
        return (_handoff_plan(index, hard)
                if hard in set(index.get("handoff_categories") or ())
                else _escalation_plan(index, hard))
    if category in set((deps.playbooks or {}).get("never_saved") or ()) \
            or ((deps.playbooks or {}).get("categories") or {}).get(category) == "not_council":
        return _escalation_plan(deps.playbooks or {}, category)
    return _plan("new_report", "log", ["unclear_other"],
                 patch={"set": {"category_id": "unclear_other"}},
                 reasons=["category_repair"])


def fallback_plan(state, deps):
    """The last honest action after a hard policy failure."""
    index = deps.playbooks or {}
    text = (state.get("inbound") or {}).get("text") or ""
    plan = state.get("plan") or {}
    if is_challenge(text) or plan.get("dialogue_act") == "challenge_previous_claim":
        return _plan("other", "answer", [plan.get("service_candidates") or ["unclear_other"]][0],
                     fact_request={"question": text, "category_id": "general"},
                     retracted=plan.get("retracted_claims") or [],
                     reasons=["challenge"])
    hard = hard_route(((state.get("inbound") or {}).get("text") or ""))
    if hard:
        return (_handoff_plan(index, hard)
                if hard in set(index.get("handoff_categories") or ())
                else _escalation_plan(index, hard))
    category = _proposed_category(state)
    if category in set(index.get("never_saved") or ()) \
            or (index.get("categories") or {}).get(category) == "not_council":
        return _escalation_plan(index, category)
    if "capture.lost" in {item.get("code") for item in state.get("violations") or []}:
        return _plan("other", "ask", ["unclear_other"],
                     clarification={"field": "description",
                                    "reason": "Tell me what the problem is."})
    if "policy.answer_ungrounded" in {item.get("code") for item in state.get("violations") or []}:
        destination = ((index.get("guidance") or {}).get("find_your_council") or {}).get("url")
        return _plan("question", "escalate", [category or "general"],
                     escalation={"kind": "council_finder", "destination": destination},
                     reasons=["ungrounded"])
    return _plan("new_report", "log", ["unclear_other"],
                 patch={"set": {"category_id": "unclear_other"}},
                 reasons=["fallback"])


def brief(state, deps):
    """The compact JSON brief the decision model may read. No raw phone, no chat id."""
    draft = state.get("incident_draft") or {}
    index = deps.playbooks or {}
    inbound = state.get("inbound") or {}
    text = (inbound.get("text") or "").strip()
    guesses = candidates_for(text, index)
    compact_books = []
    for category in dict.fromkeys(guesses + [draft.get("category_id") or "unclear_other"]):
        book = playbook(category)
        if not book:
            continue
        compact_books.append({
            "id": category,
            "label": book.get("label"),
            "outcome": book.get("outcome"),
            "save": book.get("save"),
            "allowed_questions": book.get("allowed_question_fields") or [],
            "required_local": book.get("required_local") or [],
            "location_mode": book.get("location_mode"),
            "form_url": book.get("form_url"),
            "redirect_to": book.get("redirect_to"),
            "facts": [{key: fact.get(key) for key in ("id", "fact", "url", "date")}
                      for fact in (book.get("facts") or [])[:4]],
        })
    conversation = state.get("conversation") or []
    last_agent = next((item.get("text") for item in reversed(conversation)
                       if item.get("role") == "agent"), None)
    profile = state.get("profile") or {}
    payload = {
        "message": text,
        "photo": bool(draft.get("attachments")),
        "conversation": conversation,
        "last_agent_question": last_agent,
        "profile": profile,
        "recent": [item.get("text") for item in (state.get("recent_messages") or [])[-6:]],
        "draft": {
            "description": draft.get("description"),
            "category_id": draft.get("category_id"),
            "location": (draft.get("location") or {}).get("text"),
            "capture_state": draft.get("capture_state"),
            "routing_status": draft.get("routing_status"),
        },
        "pending_question": state.get("pending_question"),
        "last_claims": state.get("last_claims_sent") or [],
        "candidates": guesses,
        "categories": [{"id": key, "outcome": value}
                       for key, value in (index.get("categories") or {}).items()],
        "evidence": [evidence.as_fact(row) for row in evidence.search(text, limit=4)],
        "task": state.get("task"),
        "playbooks": compact_books,
        "violations": [f"{item.get('code')}:{item.get('field') or ''} {item.get('message') or ''}".strip()
                       for item in (state.get("violations") or [])],
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def parse(reply):
    """Parse one model reply, tolerating a fenced block. Returns (plan, problems)."""
    body = (reply or "").strip()
    if body.startswith("```"):
        body = re.sub(r"^```(?:json)?\s*", "", body)
        body = re.sub(r"\s*```$", "", body)
    start, end = body.find("{"), body.rfind("}")
    if start >= 0 and end > start:
        body = body[start:end + 1]
    try:
        raw = json.loads(body)
    except (ValueError, TypeError):
        return None, ["schema.invalid"]
    if isinstance(raw, dict):
        action = raw.get("action")
        if raw.get("task_request") and action in ("ask", "answer"):
            raw["dialogue_act"] = "other"
        if raw.get("task_request") and action == "ask" and not raw.get("clarification"):
            raw["clarification"] = {"field": "name", "reason": "What is your name?"}
        if action != "ask":
            raw["clarification"] = None
        if action != "answer":
            raw["fact_request"] = None
        if action != "escalate":
            raw["escalation"] = None
        if raw.get("incident_patch") == {}:
            raw["incident_patch"] = None
        if action == "answer" and raw.get("fact_request") is None:
            raw["fact_request"] = {"question": "the resident's question",
                                   "category_id": "general"}
    patch = raw.get("incident_patch") if isinstance(raw, dict) else None
    sets = patch.get("set") if isinstance(patch, dict) else None
    if isinstance(sets, dict) and isinstance(sets.get("location"), str)             and sets["location"].strip():
        place = sets["location"].strip()
        sets["location"] = {"text": place, "street": place, "provenance": "text"}
    return schemas.validate_turn_plan(raw)

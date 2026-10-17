"""The resident's voice: the same facts, said like a person.

Nine reply paths in messages.py return fixed templates. This module asks the
model for the same message in a friendlier register, then checks that message
against the facts before a single word of it is sent. The template is the
fallback on any doubt, so a resident always gets a correct reply.

  brief(kind, facts)          what happened, what must appear, what is banned
  speak_name(category_id)     the casual name a person would use out loud
  generate(brief)             one model call, JSON {"text": "..."}
  lint(text, brief)           [] means safe to send
  say(kind, facts, template)  the voiced reply, or the template unchanged

Register: a friendly young council employee texting from their phone. British
English, contractions, casual but helpful, no slang that will date by next week.

The model never writes the link. say() appends "Follow it: <link>" itself, the
same pattern as rag.source_line, so the token cannot be forged or duplicated.
The examples in SYSTEM set the tone; lint is what enforces the facts.
"""

import json
import re
from functools import lru_cache
from pathlib import Path

import llm

AGENT_DIR = Path(__file__).resolve().parent.parent / "agent"
BOOK = AGENT_DIR / "categories.json"
COUNCIL_NAME = "southampton city council"

MAX_CHARS = 300
MAX_LINES = 3
TEMPERATURE = 0.9
MAX_TOKENS = 160
EMERGENCY_LEAD = "Call 999 now."
FALLBACK_SPOKEN = "report"

# "litter / street needs cleaning" cannot be said out loud, so every category
# gets the name a person would actually use. The dashboard keeps the label.
SPOKEN_NAMES = {
    "fly_tipping": "fly-tipping",
    "dog_fouling": "dog fouling",
    "dead_animal": "dead animal",
    "litter_street_cleaning": "litter",
    "graffiti_flyposting": "graffiti",
    "glass_spillage_hazard": "broken glass",
    "pothole": "pothole",
    "abandoned_vehicle": "abandoned car",
    "illegal_parking": "parking problem",
    "noise_nuisance": "noise complaint",
    "other_nuisance": "neighbour nuisance",
    "property_concern": "property concern",
    "missed_bin": "bin collection",
    "lost_damaged_bin": "bin",
    "council_housing_repair": "repair",
    "info_student_waste_rules": "bin rules",
    "flooding_severe_weather": "flooding",
    "not_council_trunk_road": "motorway problem",
    "not_council_utility": "utility problem",
    "outside_southampton": "out of area report",
    "unclear_other": "report",
    "council_service_other": "council question",
}

SITUATIONS = {
    "saved": "You have just saved a new report for this resident.",
    "duplicate": "The report matches one already open, and theirs is linked to it.",
    "incomplete": "The report is saved but the street is missing. Ask for it once.",
    "not_council": "This is not the council's job. Say so, and give who to contact.",
    "no_answer": "There is no checked answer to their question. Admit that.",
    "unclear": "The message could not be read. Ask for the problem and the street.",
    "greeting": "They said hello. Offer to take a street problem.",
    "status": "They asked for an update on their own report. Give the status.",
    "photo_added": "A photo arrived for a report already open. Confirm it landed.",
    "photo_not_report": "A photo shows something the council cannot act on. Nothing was saved.",
    "emergency": f"This may be an emergency. The first line is fixed: {EMERGENCY_LEAD}",
}

# The corporate register, banned outright. Lower case, matched after _norm.
CORPORATE = (
    "please be advised",
    "we apologise for any inconvenience",
    "do not hesitate",
    "kindly",
    "further to your enquiry",
    "thank you for your patience",
    "i understand how you feel",
)
INTERESTED = "interested in"

PHOTO_ASKS = (
    "send a photo",
    "grab a photo",
    "send one over",
    "send it over",
    "send a pic",
)

# (name, pattern). A promised timescale is a promise we cannot keep.
TIMESCALES = (
    ("within", re.compile(r"\bwithin\b", re.I)),
    ("counted", re.compile(
        r"\bin\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s*"
        r"(hours?|hrs?|days?|weeks?|working days?)\b", re.I)),
    ("finished", re.compile(
        r"\b(will|'ll|shall)\s+(be\s+)?(fixed|cleared|repaired|sorted|done|collected|emptied)\b",
        re.I)),
    ("guarantee", re.compile(r"\bguarantee\b", re.I)),
    ("by_day", re.compile(
        r"\bby\s+(tomorrow|today|monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
        r"the end of)\b", re.I)),
)

URLISH = re.compile(r"https?://|www\.|google\.|search\?q=", re.I)
MARKDOWN = re.compile(r"[*_#`]")
REPORT_ID = re.compile(r"\bR-\d{4}\b", re.I)
EM_DASH = "\u2014"
_LEAD_AH = re.compile(r"^\s*ah[\s,!\-.]+", re.I)
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)

RETRY = ("\n\nYour previous reply could not be read as JSON. Reply with the JSON "
         "object only, no other words.")

SYSTEM = (
    "You write one text message for a resident, on behalf of Southampton City Council's "
    "text line.\n"
    "You are a friendly young council employee texting from your phone. British English, "
    "contractions, plain words, calm and helpful. Casual, never slang that will date.\n"
    "The brief is JSON: what just happened, the facts you may use, and the rules.\n"
    "\n"
    "Rules:\n"
    "- Use only the facts in the brief. Invent nothing: no other street, number, team or "
    "promise.\n"
    "- Every string in must_contain has to appear in your text, spelled the same way.\n"
    "- Your text needs at least one phrase from must_any, so the meaning is unmistakable.\n"
    "- Use none of the banned phrases. Never promise a time, never say a job will be done.\n"
    "- Never write a web address, a link, or a phone number that is not in the facts.\n"
    "- Say what happened first, in the opening words. Then what happens next, or what you "
    "need.\n"
    "- No markdown, no bullet points, no emoji, no em dashes.\n"
    f"- Under {MAX_CHARS} characters, {MAX_LINES} short lines at most.\n"
    "- If ask is true, ask once for a photo, folded into the same message.\n"
    "- Say you are not sure rather than guess.\n"
    "\n"
    "Tone, in the owner's own examples. Change the words to fit the brief, keep the tone:\n"
    '- "nice one, that\'s logged - pothole on Weston Lane. if you can grab a photo, send '
    'it over."\n'
    '- "someone\'s already reported that one, so i\'ve linked yours to it."\n'
    '- "ah that one\'s not ours, sorry. National Highways handles motorways, give them a '
    'ring on 0300 123 5000."\n'
    '- "honestly i\'m not sure on that one, but the council page will have it."\n'
    '- "got it, pothole logged. whereabouts is it? a street and the nearest number is plenty."\n'
    "\n"
    'Reply with one JSON object and nothing else: {"text": "your message"}'
)


@lru_cache(maxsize=1)
def _book():
    return json.loads(BOOK.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _team_parts():
    """Our labels for teams the council has never confirmed to us."""
    parts = set()
    for category in _book()["categories"]:
        team = (category.get("team") or "").strip()
        if not team or category.get("team_confirmed"):
            continue
        if team.lower() == COUNCIL_NAME:
            continue  # naming the council is not claiming one of its teams
        for part in team.split("/"):
            part = part.split("(")[0].strip().lower()
            if len(part) > 3:
                parts.add(part)
    return frozenset(parts)


def speak_name(category_id):
    """The casual name a person would say, never the database label."""
    return SPOKEN_NAMES.get((category_id or "").strip().lower(), FALLBACK_SPOKEN)


def _clean(value):
    if value is None or isinstance(value, bool):
        return ""
    return " ".join(str(value).split())


def _norm(text):
    """Case, curly apostrophes and a leading 'ah' must never fail a good reply."""
    text = (text or "").replace("\u2019", "'").replace("\u2018", "'")
    text = _LEAD_AH.sub("", text)
    return " ".join(text.lower().split())


def _numbers(text):
    return re.findall(r"\d+", text or "")


def _allowed_numbers(facts):
    """Digits a reply may contain: only those already in the facts we hold."""
    allowed = set()
    for key, value in (facts or {}).items():
        if key == "link":  # the model never sees the link
            continue
        allowed.update(_numbers(_clean(value)))
    return allowed


def brief(kind, facts=None):
    """What happened, the facts we control, and the rules the reply must meet."""
    facts = dict(facts or {})
    kind = (kind or "").strip().lower()
    spoken = speak_name(facts.get("category_id")) if facts.get("category_id") else ""
    location = _clean(facts.get("location"))
    status_text = _clean(facts.get("status_text"))
    org = _clean(facts.get("org"))
    contact = _clean(facts.get("contact"))
    has_photo = bool(facts.get("has_photo"))
    ask = False
    banned = []

    if kind == "saved":
        must_contain = [spoken, location]
        must_any = ["logged", "noted", "reported", "on the list"]
        ask = not has_photo
        banned = list(PHOTO_ASKS) if has_photo else []
    elif kind == "duplicate":
        must_contain = [spoken, location]
        must_any = ["already", "someone", "first"]
        ask = not has_photo
        banned = list(PHOTO_ASKS) if has_photo else []
    elif kind == "incomplete":
        must_contain = [spoken]
        must_any = ["logged", "got it", "noted", "saved", "on the list"]
    elif kind == "not_council":
        must_contain = [org, contact]
        must_any = ["not ours", "not the council", "not us", "someone else", "isn't ours"]
        banned = ["we'll fix", "we will fix", "our crew", "we'll send"]
    elif kind == "no_answer":
        must_contain = []
        must_any = ["not sure", "don't have", "can't check", "no checked", "not certain"]
        banned = ["definitely"]
    elif kind == "unclear":
        must_contain = []
        must_any = ["didn't catch", "not sure", "tell me", "say that", "again"]
    elif kind == "greeting":
        must_contain = []
        must_any = ["send", "tell me", "text me", "log"]
    elif kind == "status":
        must_contain = [spoken, location, status_text]
        must_any = ["update", "status", "looking at", "resolved", "now", "still"]
    elif kind == "photo_added":
        must_contain = []
        must_any = ["photo", "pic", "picture"]
        banned = list(PHOTO_ASKS)
    elif kind == "photo_not_report":
        must_contain = []
        must_any = ["not something", "nothing", "not ours", "can't act"]
    elif kind == "emergency":
        must_contain = ["999"] + ([contact] if contact and contact != "999" else [])
        must_any = ["999", "call"]
        banned = ["don't call", "no need to call", "wait for"]
    else:
        raise ValueError(f"unknown kind: {kind!r}")

    must_contain = [item for item in must_contain if item]
    allowed = _allowed_numbers(facts)
    for item in must_contain:
        allowed.update(_numbers(item))

    return {
        "kind": kind,
        "situation": SITUATIONS[kind],
        "spoken_name": spoken,
        "category_label": _clean(facts.get("category_label")),
        "location": location,
        "status_text": status_text,
        "org": org,
        "contact": contact,
        "page": _clean(facts.get("page")),
        "has_photo": has_photo,
        "group": _clean(facts.get("group")),
        "must_contain": must_contain,
        "must_any": must_any,
        "banned": banned,
        "allowed_numbers": sorted(allowed),
        "limits": {"max_chars": MAX_CHARS, "max_lines": MAX_LINES},
        "ask": ask,
    }


def _json_object(raw):
    """Pull the first JSON object out of a model reply, fenced or wrapped in prose."""
    if not raw:
        return None
    fenced = _FENCE.search(raw)
    text = fenced.group(1) if fenced else raw
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        value = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def generate(brief_data):
    """One model call. None when no model answered or the JSON was unreadable."""
    user = json.dumps(brief_data, ensure_ascii=False, sort_keys=True)
    reply, mode = llm.chat(SYSTEM, user, max_tokens=MAX_TOKENS, temperature=TEMPERATURE)
    data = _json_object(reply) if mode == "model" else None
    if data is None and mode == "model":
        reply, mode = llm.chat(SYSTEM, user + RETRY, max_tokens=MAX_TOKENS,
                               temperature=TEMPERATURE)
        data = _json_object(reply) if mode == "model" else None
    if data is None:
        return None
    # One paragraph: iMessage wraps it, and a stray newline would eat a line of
    # the three we allow.
    return " ".join(str(data.get("text") or "").split()) or None


def lint(text, brief_data):
    """Every rule in one place. [] means safe to send."""
    body = (text or "").strip()
    if not body:
        return ["empty"]

    limits = brief_data.get("limits") or {}
    max_chars = int(limits.get("max_chars") or MAX_CHARS)
    max_lines = int(limits.get("max_lines") or MAX_LINES)
    problems = []

    if len(body) > max_chars:
        problems.append(f"too_long:{len(body)}")
    lines = [line for line in body.splitlines() if line.strip()]
    if len(lines) > max_lines:
        problems.append(f"too_many_lines:{len(lines)}")
    if URLISH.search(body):
        problems.append("url")
    if MARKDOWN.search(body):
        problems.append("markdown")
    if EM_DASH in body:
        problems.append("em_dash")
    if REPORT_ID.search(body):
        problems.append("report_id")

    flat = _norm(body)
    for phrase in CORPORATE:
        if phrase in flat:
            problems.append("corporate:" + phrase)
    if INTERESTED in flat:
        problems.append("interested_in")
    for name, pattern in TIMESCALES:
        if pattern.search(flat):
            problems.append("timescale:" + name)

    allowed = set(str(number) for number in brief_data.get("allowed_numbers") or [])
    for required in brief_data.get("must_contain") or []:
        allowed.update(_numbers(str(required)))
    for run in _numbers(flat):
        if run not in allowed:
            problems.append("number:" + run)

    # "National Highways" is a real organisation and may be named; "Highways
    # team" is one of our own unconfirmed labels and may not.
    team_text = flat
    teams = _team_parts()
    for name in teams:
        team_text = re.sub(r"national\s+" + re.escape(name), " ", team_text)
    for name in sorted(teams):
        if re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", team_text):
            problems.append("team:" + name)

    for required in brief_data.get("must_contain") or []:
        if _norm(str(required)) not in flat:
            problems.append("missing:" + str(required))
    wanted = brief_data.get("must_any") or []
    if wanted and not any(_norm(str(phrase)) in flat for phrase in wanted):
        problems.append("no_meaning:" + "|".join(str(phrase) for phrase in wanted))
    for phrase in brief_data.get("banned") or []:
        if _norm(str(phrase)) in flat:
            problems.append("banned:" + str(phrase))

    if brief_data.get("kind") == "incomplete" and body.count("?") != 1:
        problems.append(f"questions:{body.count('?')}")
    if brief_data.get("kind") == "emergency" and not body.startswith(EMERGENCY_LEAD):
        problems.append("emergency_lead")
    return problems


def say(kind, facts, template):
    """The voiced reply, or the template unchanged. Never a partial sentence."""
    try:
        brief_data = brief(kind, facts)
        text = generate(brief_data)
    except Exception as error:  # noqa: BLE001 - a reply must always go out
        print(f"[voice] fallback {kind} error:{error}")
        return template

    if not text:
        print(f"[voice] fallback {kind} no_text")
        return template

    problems = lint(text, brief_data)
    if problems:
        print(f"[voice] fallback {kind} {' '.join(problems)}")
        return template

    link = _clean((facts or {}).get("link"))
    if not link:
        return text
    label = _clean((facts or {}).get("link_label")) or "Follow it"
    return f"{text}\n{label}: {link}"


if __name__ == "__main__":
    examples = {
        "saved": {"category_id": "pothole", "location": "Weston Lane", "has_photo": False},
        "duplicate": {"category_id": "pothole", "location": "Weston Lane"},
        "incomplete": {"category_id": "pothole"},
        "not_council": {"category_id": "not_council_trunk_road",
                        "org": "National Highways", "contact": "0300 123 5000"},
        "no_answer": {"category_id": "council_service_other",
                      "page": "https://www.southampton.gov.uk/contact-us/online-forms"},
        "status": {"category_id": "pothole", "location": "Weston Lane",
                   "status_text": "being looked at by the council",
                   "link": "http://localhost:5005/r/token123"},
    }
    for kind, facts in examples.items():
        data = brief(kind, facts)
        text = generate(data)
        print(f"{kind}: {text!r}")
        if text:
            print(f"  lint: {lint(text, data)}")

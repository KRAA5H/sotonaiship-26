"""Structured photo analysis: the one place the feature shape is defined.

Every photo becomes the same five fields, so the officer sees features rather
than prose and the priority score can use them:

  what_is_visible  short plain sentence, max 240 characters
  estimated_size   small | medium | large | unknown
  surface          road | pavement | private land | other | unknown
  hazard           yes | no | unknown
  label            at most 6 words

validate() checks whatever the model returns against this shape and fixes or
rejects anything that does not fit. It also enforces the location rule: the
analysis must never invent or guess where a photo was taken. There is no
location field, extra keys are dropped, and a text field that names a street,
postcode, area or coordinates is rejected rather than kept.

analyse() is the call to the vision model. Nothing calls it yet: the model and
its cost are waiting for a go-ahead, and the webhook does not store photos.
"""

import json
import re

ESTIMATED_SIZE = ("small", "medium", "large", "unknown")
SURFACE = ("road", "pavement", "private land", "other", "unknown")
HAZARD = ("yes", "no", "unknown")
FIELDS = ("what_is_visible", "estimated_size", "surface", "hazard", "label")
MAX_VISIBLE = 240
MAX_LABEL_WORDS = 6

SYNONYMS = {
    "surface": {"footpath": "pavement", "sidewalk": "pavement", "footway": "pavement", "path": "pavement",
                "carriageway": "road", "street": "road", "private": "private land", "garden": "private land",
                "driveway": "private land"},
    "hazard": {"true": "yes", "false": "no", "y": "yes", "n": "no"},
    "estimated_size": {"big": "large", "huge": "large", "tiny": "small", "minor": "small"},
}

SYSTEM = (
    "You look at one photo a resident sent to Southampton City Council and describe only what is in it. "
    "Reply with a JSON object and nothing else, with exactly these keys: "
    '"what_is_visible" (one short plain sentence), '
    '"estimated_size" ("small", "medium", "large" or "unknown"), '
    '"surface" ("road", "pavement", "private land", "other" or "unknown"), '
    '"hazard" ("yes", "no" or "unknown": could it hurt someone or damage a vehicle?), '
    '"label" (at most 6 words). '
    "Never say where the photo was taken. Do not name or guess a street, area, postcode, landmark, "
    "business or town, even if you think you can tell. Do not describe people. "
    'If you are not sure about a field, use "unknown".'
)

# Anything that reads as a place. A field containing one is rejected.
_PLACE_PATTERNS = [
    re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", re.I),                          # UK postcode
    re.compile(r"\b(?:[A-Z][a-z]+\s+)+(?:Road|Rd|Street|St|Lane|Ln|Avenue|Ave|Close|Drive|Way|"
               r"Crescent|Terrace|Place|Gardens|Grove|Hill|Square|Parade|Walk|Court|Row|Mews)\b"),  # named street
    re.compile(r"-?\d{1,3}\.\d{3,}\s*,\s*-?\d{1,3}\.\d{3,}"),                              # coordinates
    re.compile(r"\b(?:Southampton|Hampshire|Eastleigh|Totton|Portswood|Shirley|Bitterne|Sholing|"
               r"Woolston|Highfield|Bassett|Swaythling|Lordshill|Millbrook|Redbridge|Thornhill|"
               r"Weston|Freemantle|Polygon|Northam|St Denys|Ocean Village|Bevois)\b", re.I),  # places
]
_LOCATION_KEYS = re.compile(r"locat|address|street|road|postcode|post_code|area|place|lat|lon|coord|where",
                            re.I)


def names_a_place(text):
    return any(p.search(text or "") for p in _PLACE_PATTERNS)


def _parse(raw):
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _choice(name, value, allowed, problems):
    word = str(value if value is not None else "").strip().lower()
    if isinstance(value, bool):
        word = "yes" if value else "no"
    word = SYNONYMS.get(name, {}).get(word, word)
    if word in allowed:
        return word
    problems.append(f"{name}: {value!r} is not one of {', '.join(allowed)}; set to unknown")
    return "unknown"


def validate(raw):
    """(features, problems). features is None only when nothing usable came back."""
    data = _parse(raw)
    if data is None:
        return None, ["the model reply was not a JSON object"]

    problems = []
    for key in data:
        if key not in FIELDS:
            kind = "location" if _LOCATION_KEYS.search(key) else "unknown"
            problems.append(f"dropped {kind} field {key!r}")

    visible = " ".join(str(data.get("what_is_visible") or "").split())[:MAX_VISIBLE] or None
    if visible and names_a_place(visible):
        problems.append("what_is_visible named a place; rejected")
        visible = None

    label_words = re.sub(r"[^\w\s'-]", " ", str(data.get("label") or "")).split()
    if len(label_words) > MAX_LABEL_WORDS:
        problems.append(f"label cut to {MAX_LABEL_WORDS} words")
    label = " ".join(label_words[:MAX_LABEL_WORDS]) or None
    if label and names_a_place(label):
        problems.append("label named a place; rejected")
        label = None

    features = {
        "what_is_visible": visible,
        "estimated_size": _choice("estimated_size", data.get("estimated_size"), ESTIMATED_SIZE, problems),
        "surface": _choice("surface", data.get("surface"), SURFACE, problems),
        "hazard": _choice("hazard", data.get("hazard"), HAZARD, problems),
        "label": label,
    }
    if not visible and not label and all(features[k] == "unknown" for k in ("estimated_size", "surface", "hazard")):
        return None, problems + ["nothing usable left"]
    return features, problems


def from_stored(value):
    """Features read back from the database, validated again. None if absent or unusable."""
    if not value:
        return None
    return validate(value)[0]


def analyse(image, chat=None):
    """Ask the vision model for the features of one photo. Not wired in yet.

    image is (bytes, mime). chat defaults to llm.chat; pass a fake in tests.
    Returns {"features", "problems", "mode"}. Never returns a location.
    """
    if chat is None:
        import llm  # noqa: PLC0415  (only when a real call is wanted)
        chat = llm.chat
    reply, mode = chat(SYSTEM, "Describe this photo as the JSON object.", image)
    features, problems = validate(reply)
    return {"features": features, "problems": problems, "mode": mode}

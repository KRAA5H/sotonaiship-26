"""Southampton geography, offline: the city boundary and its street names.

Everything here is local and fast: no network call, so the location agent can
answer in well under a millisecond and nothing a resident types leaves our server.

  in_city(lat, lng)          True / False from the council's real boundary,
                             None if the boundary file is missing
  normalise(text)            "12 Lawn Road." -> "12 lawn rd"
  find_streets(query, n)     ranked street suggestions for a typed prefix
  street_in_text(text)       every stretch of the street named in free text
  area_in_text(rows, text)   which of those stretches the text means
  coords_in_text(text)       lat, lng from an Apple / Google Maps link, a geo:
                             URI or a shared-location card (.loc.vcf)
  names_outside_place(text)  a town outside the city that the text names
  postcode_in_text(text)     the first UK postcode in the text

Data: southampton_boundary.json and southampton_streets.json, built by
build_gazetteer.py from OpenStreetMap ((c) OpenStreetMap contributors, ODbL).
"""

import json
import re
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
BOUNDARY_FILE = HERE / "southampton_boundary.json"
STREETS_FILE = HERE / "southampton_streets.json"

# Everything is compared in one canonical short form, so "Lawn Road", "lawn rd"
# and "Lawn Rd." are the same, and "St" matches both Street and Saint.
SHORT = {
    "road": "rd", "street": "st", "saint": "st", "avenue": "ave", "av": "ave", "lane": "ln",
    "close": "cl", "drive": "dr", "crescent": "cres", "cr": "cres", "gardens": "gdns",
    "garden": "gdns", "gdn": "gdns", "place": "pl", "square": "sq", "terrace": "tce", "terr": "tce",
    "court": "ct", "grove": "gr", "gro": "gr", "park": "pk", "hill": "hl", "way": "wy",
    "parade": "pde", "mews": "mws", "walk": "wk", "highway": "hwy", "roundabout": "rdbt",
    "north": "n", "nth": "n", "south": "s", "sth": "s", "east": "e", "west": "w",
}

# Towns and districts outside the city that residents name. Southampton's own
# areas (Bitterne, Woolston, Portswood...) are deliberately absent.
OUTSIDE_PLACES = (
    "eastleigh", "totton", "romsey", "winchester", "portsmouth", "fareham", "hedge end",
    "chandler's ford", "chandlers ford", "west end", "netley", "hamble", "bursledon",
    "marchwood", "hythe", "fawley", "ashurst", "lyndhurst", "botley", "north baddesley",
    "nursling", "rownhams", "fair oak", "bishopstoke", "locks heath", "new forest",
    "isle of wight", "lymington", "andover", "basingstoke", "bournemouth", "poole",
    "salisbury", "havant", "gosport", "waterlooville", "london",
)

POSTCODE = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?)\s*(\d[A-Z]{2})\b", re.I)
_NUM = r"(-?\d{1,3}\.\d{3,})"
# vCards (iMessage "Send My Current Location") escape the comma as "\,".
_SEP = r"\s*\\?(?:,|%2C)\s*"
COORDS = [
    re.compile(r"(?:coordinate|ll|center|sll|q|query|daddr|saddr|destination)=" + _NUM + _SEP + _NUM, re.I),
    re.compile(r"/@" + _NUM + "," + _NUM, re.I),          # google.com/maps/@lat,lng,17z
    re.compile(r"geo:" + _NUM + _SEP + _NUM, re.I),        # geo: URIs
]


# ---------------------------------------------------------------------------
# Boundary
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _boundary():
    try:
        data = json.loads(BOUNDARY_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    outer = [[(p[0], p[1]) for p in ring] for ring in data.get("outer") or []]
    inner = [[(p[0], p[1]) for p in ring] for ring in data.get("inner") or []]
    if not outer:
        return None
    boxes = [(min(p[0] for p in r), max(p[0] for p in r), min(p[1] for p in r), max(p[1] for p in r))
             for r in outer]
    return outer, inner, boxes


def _in_ring(lat, lng, ring):
    """Ray casting. Points are (lat, lng)."""
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        yi, xi = ring[i]
        yj, xj = ring[j]
        if (yi > lat) != (yj > lat) and lng < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def in_city(lat, lng):
    """True if the point is inside Southampton City Council's boundary."""
    data = _boundary()
    if data is None:
        return None
    outer, inner, boxes = data
    for ring, (south, north, west, east) in zip(outer, boxes):
        if south <= lat <= north and west <= lng <= east and _in_ring(lat, lng, ring):
            return not any(_in_ring(lat, lng, hole) for hole in inner)
    return False


# ---------------------------------------------------------------------------
# Streets
# ---------------------------------------------------------------------------
def normalise(text):
    """Lower case, no punctuation, canonical short forms: '12 Lawn Road.' -> '12 lawn rd'."""
    text = (text or "").lower().replace("'", "").replace("’", "")
    return " ".join(SHORT.get(word, word) for word in re.findall(r"[a-z0-9]+", text))


@lru_cache(maxsize=1)
def _streets():
    """[(name, area, lat, lng, normalised name)], one per (name, area)."""
    try:
        rows = json.loads(STREETS_FILE.read_text(encoding="utf-8"))["streets"]
    except (OSError, ValueError, KeyError):
        return []
    seen, out = set(), []
    for name, area, lat, lng in rows:
        if (name, area) in seen:
            continue
        seen.add((name, area))
        out.append((name, area, lat, lng, normalise(name)))
    return out


@lru_cache(maxsize=1)
def _by_length():
    """Longest names first, so 'Portswood Road' wins over 'Portswood'."""
    return sorted(_streets(), key=lambda s: -len(s[4]))


def street_count():
    return len(_streets())


def _as_dict(row):
    name, area, lat, lng, _ = row
    return {"street": name, "area": area, "lat": lat, "lng": lng,
            "label": f"{name}, {area}" if area else name}


def find_streets(query, limit=8):
    """Suggestions for what someone is typing. Starts-with beats word-start beats contains."""
    q = normalise(query)
    if len(q) < 2:
        return []
    scored = []
    for row in _streets():
        name = row[4]
        if name.startswith(q):
            rank = 0
        elif (" " + q) in (" " + name):
            rank = 1
        elif q in name:
            rank = 2
        else:
            continue
        scored.append((rank, row[0].lower(), row[1], row))
    # Within a rank, alphabetical, the way a drop-down reads.
    scored.sort(key=lambda s: s[:3])
    return [_as_dict(s[3]) for s in scored[:limit]]


def street_in_text(text):
    """Every stretch of the longest street named in the text: 'outside 12 lawn rd' -> Lawn Road.

    Returns one entry per area the street runs through, or [] if no Southampton
    street is named. Whole words only, so 'lawn' alone never matches.
    """
    flat = " " + normalise(text) + " "
    if len(flat) < 6:
        return []
    for row in _by_length():
        name = row[4]
        if len(name) < 5 or " " not in name:
            continue  # one-word names like "Broadway" are too easy to hit by accident
        if f" {name} " in flat:
            return [_as_dict(r) for r in _streets() if r[4] == name]
    return []


def area_in_text(rows, text):
    """When a street runs through several areas, pick the one the text names, else None."""
    flat = " " + normalise(text) + " "
    for row in rows:
        if row["area"] and f" {normalise(row['area'])} " in flat:
            return row
    return None


# ---------------------------------------------------------------------------
# Shared locations and places outside the city
# ---------------------------------------------------------------------------
def coords_in_text(text):
    """(lat, lng) from a maps link, a geo: URI or a shared-location card, else None."""
    for pattern in COORDS:
        match = pattern.search(text or "")
        if not match:
            continue
        try:
            lat, lng = float(match.group(1)), float(match.group(2))
        except ValueError:
            continue
        if -90 <= lat <= 90 and -180 <= lng <= 180:
            return lat, lng
    return None


def names_outside_place(text):
    """The first town outside the city that the text names, or None.

    Words that belong to a Southampton street in the same text do not count:
    "West End Road" and "Romsey Road" are city streets, not the towns.
    """
    # Compare in the normalised form, where "road" and "rd" are the same word.
    flat = " " + normalise(text) + " "
    for row in street_in_text(text):
        flat = flat.replace(" " + normalise(row["street"]) + " ", " ")
    for place in OUTSIDE_PLACES:
        if " " + normalise(place) + " " in flat:
            return place
    return None


def postcode_in_text(text):
    match = POSTCODE.search(text or "")
    return f"{match.group(1).upper()} {match.group(2).upper()}" if match else None

"""Location agent: where the problem is, three ways, checked against the real city.

When a report has no usable location it offers three ways, all ending in the
same report:
  1. tap the map link: drop a pin, search a street from a drop-down, or use
     "my current location" (pin_service.py, served on the bot's own address)
  2. reply with the street name: matched offline against every Southampton street
  3. share a location: an Apple or Google Maps pin, or iMessage's "Send My
     Current Location" card

Every location is checked against Southampton City Council's real boundary
(geo/southampton_boundary.json), never a postcode prefix: some SO postcodes are
Eastleigh or Totton. Only the street is kept, never coordinates.

No model call: everything here is local and takes well under a millisecond,
apart from one reverse lookup when a pin arrives.
"""

import math
import re

import location as location_service   # code/location.py: Nominatim reverse geocoding
import pin_service
from geo import southampton as city

FOLLOW_UP_CHARS = 80   # a reply longer than this is a new message, not "which street"
NEAREST_STREET_METRES = 200

CARD_SUFFIXES = (".loc.vcf", ".vcf")
CARD_TYPES = ("text/x-vlocation", "text/vcard", "text/x-vcard")


def is_location_card(attachment):
    """iMessage's "Send My Current Location" arrives as a small vCard."""
    name = (attachment.get("transferName") or "").lower()
    mime = (attachment.get("mimeType") or "").lower()
    return name.endswith(CARD_SUFFIXES) or any(kind in mime for kind in CARD_TYPES)


def _metres(a, b):
    dx = (a[1] - b[1]) * 111320 * math.cos(math.radians((a[0] + b[0]) / 2))
    dy = (a[0] - b[0]) * 110540
    return math.hypot(dx, dy)


def nearest_street(lat, lng, limit=NEAREST_STREET_METRES):
    """The closest street in the offline list, for when the reverse lookup is down."""
    best = None
    for name, area, s_lat, s_lng, _ in city._streets():
        d = _metres((lat, lng), (s_lat, s_lng))
        if d <= limit and (best is None or d < best[0]):
            best = (d, name, area)
    return {"street_name": best[1], "area": best[2]} if best else None


class LocationAgent:
    name = "location"

    # -- 3. a shared location -----------------------------------------------
    def shared_place(self, text, card=""):
        """A place from a maps link or a location card in this message, else None.

        Returns {"street_name", "postcode", "area", "in_city"} with no coordinates.
        """
        coords = city.coords_in_text(text) or city.coords_in_text(card)
        if not coords:
            return None
        lat, lng = coords
        inside = city.in_city(lat, lng)
        place = None
        try:
            place = location_service.LocationService().reverse_geocode(lat, lng)
        except Exception as error:  # noqa: BLE001 - a pin must never break a reply
            print(f"[place] reverse geocode failed: {error}")
        if not place or not place.get("street_name"):
            place = {**(place or {}), **(nearest_street(lat, lng) or {})}
        if not place.get("street_name"):
            return None
        if inside is None:
            # No boundary file: fall back to the postcode, the old check.
            postcode = (place.get("postcode") or "").upper()
            inside = not postcode or postcode.startswith("SO")
        print(f"[place] pin -> {place.get('street_name')} ({place.get('area')}) in_city={inside}")
        return {
            "street_name": place.get("street_name"),
            "postcode": place.get("postcode"),
            "area": place.get("area"),
            "in_city": bool(inside),
        }

    # -- 2. a typed street ------------------------------------------------------
    def street_reply(self, text):
        """A short reply that names a Southampton street, as {"street", "area", "label"}."""
        text = (text or "").strip()
        if not text or len(text) > FOLLOW_UP_CHARS or city.coords_in_text(text):
            return None
        rows = city.street_in_text(text)
        if not rows:
            return None
        # One stretch: its area is known. Several: only the area the resident named.
        named = city.area_in_text(rows, text) if len(rows) > 1 else None
        row = named or rows[0]
        area = row["area"] if (len(rows) == 1 or named) else ""
        number = re.match(r"^\s*(\d+[a-z]?)\b", text, re.IGNORECASE)
        where = f"{number.group(1)} {row['street']}" if number else row["street"]
        return {"street": row["street"], "area": area, "location": where,
                "label": f"{row['street']}, {area}" if area else row["street"]}

    # -- checking what triage found ------------------------------------------
    def resolve(self, decision, text):
        """Tidy the street triage found, and never call a street outside the city by mistake."""
        decision = dict(decision)
        said = decision.get("location") or ""
        if said:
            rows = city.street_in_text(said)
            if rows:
                row = rows[0] if len(rows) == 1 else city.area_in_text(rows, said + " " + (text or ""))
                if city.normalise(said) == city.normalise(rows[0]["street"]):
                    decision["location"] = rows[0]["street"]   # "lawn rd" -> "Lawn Road"
                if row:
                    decision["area"] = row["area"]
                decision["in_city"] = True

        # TODO 1.3: "outside Southampton" needs evidence, not a guess from a fragment.
        if decision.get("category_id") == "outside_southampton":
            evidence = city.names_outside_place(text) or self._outside_postcode(text)
            if not evidence and (city.street_in_text(text) or len((text or "").split()) <= 4):
                decision = {**decision, "reason": "unclear", "is_report": False,
                            "outcome": "unknown", "category_id": None, "category_label": None}
                print("[location] outside_southampton without evidence, asking again")
        return decision

    @staticmethod
    def _outside_postcode(text):
        postcode = city.postcode_in_text(text)
        return postcode if postcode and not postcode.startswith("SO") else None

    # -- 1. the map link ----------------------------------------------------------
    def map_link(self, report_id, base=None):
        """A two hour link to drop a pin for this report, or None if it cannot be made."""
        try:
            return pin_service.create_location_link(report_id, base=base)
        except Exception as error:  # noqa: BLE001 - the street question still works without it
            print(f"[location] no map link for {report_id}: {error}")
            return None

    @staticmethod
    def describe(place):
        """'Lawn Road, near Portswood Park' for a confirmed pin."""
        return pin_service.as_report_location(place) or ""

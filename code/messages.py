"""Every resident-facing string, in one place.

Copy rules, checked by test_messages.py:

  - the first line says what happened, not thank you
  - three short lines at most, one link, no markdown, no jargon
  - promise only what the system does today
  - name a team only if the rulebook confirms it, and it confirms none of them
  - never end with an em dash, never use the word "interested"

Nothing here talks to the model or the database. Callers pass a decision and,
where relevant, the saved report.
"""

import json
from functools import lru_cache
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent.parent / "agent"
BOOK = AGENT_DIR / "categories.json"
COUNCIL_CONTACT = "https://www.southampton.gov.uk/contact-us/online-forms"

# The four cases where it is not the council's job. Written out rather than
# assembled from labels, because "Contact: Find your local council" reads badly.
NOT_COUNCIL_COPY = {
    "national_highways": "Motorways and trunk roads are National Highways, not the council.",
    "find_your_council": "That one is not Southampton City Council's to fix.",
    "flood_warnings": "Flood warnings come from the Environment Agency.",
    "emergency": "That is an emergency, not a report.",
}


@lru_cache(maxsize=1)
def _book():
    data = json.loads(BOOK.read_text(encoding="utf-8"))
    return (
        {category["id"]: category for category in data["categories"]},
        data.get("guidance_links") or {},
        data.get("meta") or {},
    )


def _category(category_id):
    return _book()[0].get(category_id) or {}


def _label(decision):
    if decision.get("category_id") == "unclear_other":
        return "your report"
    return (
        decision.get("category_label")
        or _category(decision.get("category_id")).get("label")
        or decision.get("category_id")
        or "report"
    ).lower()


def _where(decision):
    return (decision.get("location") or "").strip()


def _join(*lines):
    return "\n".join(line.strip() for line in lines if line and line.strip())


PHOTO_ASK = "If you can send a photo, it will help."


def logged(decision, saved):
    """A report was saved. Say what, where, and what happens next."""
    head = f"Logged: {_label(decision)}"
    where = _where(decision)
    if where:
        head += f", {where}"
    has_photo = bool(decision.get("has_photo"))
    head += ". Photo attached." if has_photo else "."
    ask = "" if has_photo else PHOTO_ASK
    return _join(head, "It hasn't gone to the council yet.", ask, f"Follow it: {saved['link']}")


def duplicate(decision, saved):
    head = f"Already logged: {_label(decision)}"
    where = _where(decision)
    if where:
        head += f", {where}"
    head += "."
    ask = "" if decision.get("has_photo") else PHOTO_ASK
    return _join(
        head,
        "Your report is linked to it here.",
        ask,
        f"Follow it: {saved['link']}",
    )


def need_location(decision, map_link=None, mode="pin"):
    """Ask exactly one question, in the rulebook's own words where we have them.

    mode "pin": the street, a shared location, or the map link to drop a pin.
    mode "address": bins and housing need a house, never a pin.
    """
    questions = _category(decision.get("category_id")).get("follow_up_questions") or []
    question = (questions[0] if questions else "Where exactly is it").strip()
    if not question.endswith("?"):
        question += "?"
    if mode == "address":
        return _join(
            f"Logged: {_label(decision)}.",
            question,
            "Reply with the house number and street and I will add it.",
        )
    ask = "" if decision.get("has_photo") else PHOTO_ASK
    if map_link:
        how = f"Reply with the street, share your location, or drop a pin on the map: {map_link}"
    else:
        how = "Reply with the street and I will add it."
    return _join(f"Logged: {_label(decision)}.", question, how, ask)


def located(decision, link):
    """The street arrived after the report: from a pin, a shared location or a reply."""
    where = _where(decision) or "the spot you gave"
    return _join(f"Thanks, added: {_label(decision)} at {where}.",
                 "It hasn't gone to the council yet.", f"Follow it: {link}")


def captured(decision, saved=None, map_link=None):
    """A real report outside the confirmed categories: kept, not routed, nothing claimed."""
    where = _where(decision)
    head = "Logged it here" + (f": {where}." if where else ".")
    head += " I can't confirm which council team owns it, so it hasn't gone to the council yet."
    if where:
        line = "" if decision.get("has_photo") else PHOTO_ASK
    elif map_link:
        line = "Where is it? Reply with the street, or drop a pin on the map."
    else:
        line = "Where is it? Reply with the street and I will add it."
    link = map_link or (saved or {}).get("link")
    return _join(head, line, f"Follow it: {link}" if link else "")


def already_yours(decision, link):
    """The same person reported the same problem again. Nothing new is saved."""
    head = f"You've already reported this one: {_label(decision)}"
    where = _where(decision)
    if where:
        head += f", {where}"
    return _join(head + ".", "No need to send it again, it's still open here.", f"Follow it: {link}")


def handoff(decision, form_url):
    """Neighbour problems go to the council's own form, so we never log someone's home."""
    return _join(
        "Problems with a neighbour go through the council's own form, "
        "so an officer can follow it up with you directly.",
        "Nothing has been logged here.",
        f"Form: {form_url or COUNCIL_CONTACT}",
    )


def threat():
    """Fixed wording, never model-written."""
    return _join("I can only help with street problems here.",
                 "If anyone is in danger, call 999.")


def answered(text):
    """The grounded answer from rag.py already carries its own source line."""
    return (text or "").strip()


def no_answer(decision):
    """Never lead with what we cannot do. Offer to help, with the page as a fallback."""
    category = _category(decision.get("category_id"))
    page = (category.get("official_form_url") or category.get("answer_source")
            or COUNCIL_CONTACT)
    return _join(
        "I can help with that.",
        "Tell me a bit more about what you need and where, and I'll point you the right way.",
        f"The council's page might have it too: {page}",
    )


def not_council(decision):
    category = _category(decision.get("category_id"))
    key = category.get("redirect_to") or ""
    link = _book()[1].get(key) or {}
    lead = NOT_COUNCIL_COPY.get(key, "That one is not the council's to fix.")
    contact = (link.get("contact") or "").strip()
    url = (link.get("url") or "").strip()
    lines = [lead]
    if contact and not contact.startswith("http"):
        lines.append(f"Call {contact}.")
    if url:
        lines.append(f"Details: {url}")
    if not contact and not url:
        lines.append("Check GOV.UK for the right service.")
    return _join(*lines)


def emergency():
    return _join(
        "Call 999 now.",
        "Tell them where it is. If it is safe, reply here and I will log it too.",
    )


def unclear():
    return _join(
        "I didn't catch that.",
        "Send the problem and the street, for example: pothole outside 12 Alma Road.",
    )


def greeting():
    return _join(
        "Hello. Send a street problem and I will log it with the council.",
        "Pothole, dumped rubbish, missed bin, broken glass.",
    )


def contact_for(category_id):
    """Who else can help, and the page to send them to, from the rulebook."""
    category = _category(category_id)
    key = category.get("redirect_to") or ""
    link = _book()[1].get(key) or {}
    org = {
        "national_highways": "National Highways",
        "find_your_council": "your local council",
        "flood_warnings": "the Environment Agency",
        "emergency": "999",
    }.get(key) or (link.get("label") or "the right service")
    return {
        "org": org,
        "contact": (link.get("contact") or "").strip(),
        # "source" is where we checked the fact, not a page to send a resident to.
        "page": (link.get("url") or "").strip(),
    }


def photo_added(link):
    return _join("Photo added to your report.", f"Follow it: {link}")


def which_report(rows):
    """Two open reports, one photo. Ask, never guess."""
    names = [(row.get("location") or "").strip() or "one with no street yet"
             for row in (rows or [])[:3]]
    return _join(
        "Which one is this photo for? " + " or ".join(names) + ".",
        "Reply with the street and I will add the photo.",
    )


def sorry():
    """Something failed. Never claim a report was logged when it was not."""
    return "Something went wrong at our end. Send that again and I will log it."


def pin_received(place):
    """A shared pin arrived with no words. Keep it and ask the one question."""
    street = (place or {}).get("street_name") or "that pin"
    area = (place or {}).get("area")
    where = f"{street}, {area}" if area else street
    return _join(f"Got your pin at {where}.", "What's the problem there?")


def pin_outside(place):
    """A pin outside Southampton. Say so, then give the finder as a link."""
    street = (place or {}).get("street_name") or "that pin"
    postcode = (place or {}).get("postcode")
    where = f"{street}, {postcode}" if postcode else street
    page = contact_for("outside_southampton").get("page") or "https://www.gov.uk/find-local-council"
    return _join(f"That pin is at {where}, which is outside Southampton.",
                 f"Your own council handles it: {page}")


def thanks():
    """Silence. A reply here would be noise."""
    return ""


def status(report):
    """Plain-words status for the resident's own latest report."""
    label = _category(report.get("category_id")).get("label") or "report"
    head = f"Update on your {label.lower()}"
    where = (report.get("location") or "").strip()
    if where:
        head += f" at {where}"
    head += "."
    return _join(head, f"Status: {report.get('status_text')}.", f"Follow it: {report['link']}")

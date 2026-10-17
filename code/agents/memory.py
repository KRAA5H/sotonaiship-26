"""Short-term conversation memory shared by the agents. In process, bounded, no disk.

  PENDING   sender -> the report we asked a location for (10 minutes)
  PLACES    sender -> a pin they shared before saying what the problem is (10 minutes)
  CONTACTS  reporter_ref -> chat to reply on, so a later pin, status change or
            confirmation can reach the resident. Only the hashed reference is
            the key, and nothing here survives a restart.

blue_bubbles.py exposes these same objects as _pending and _places, so the
webhook, the simulator and the tests all see one memory.
"""

import threading
import time
from collections import OrderedDict

PENDING = OrderedDict()
PENDING_LOCK = threading.Lock()
PENDING_SECONDS = 600
PENDING_LIMIT = 200

PLACES = OrderedDict()
PLACES_LOCK = threading.Lock()
PLACE_SECONDS = 600
PLACE_LIMIT = 200

CONTACTS = OrderedDict()
CONTACTS_LOCK = threading.Lock()
CONTACTS_LIMIT = 2000


# ---------------------------------------------------------------------------
# The location question
# ---------------------------------------------------------------------------
def remember_location(sender, text, saved, decision):
    """Hold the incomplete report, so the answer becomes its street, not a new row."""
    if not sender or not text:
        return
    with PENDING_LOCK:
        PENDING[sender] = {
            "text": text,
            "asked_at": time.time(),
            "report_id": saved["report_id"],
            "link": saved["link"],
            "category_id": decision["category_id"],
            "has_photo": bool(decision.get("has_photo")),
        }
        while len(PENDING) > PENDING_LIMIT:
            PENDING.popitem(last=False)


def pending_for(sender):
    """The live pending entry for this sender, without consuming it."""
    if not sender:
        return None
    with PENDING_LOCK:
        entry = PENDING.get(sender)
    if not entry or time.time() - entry["asked_at"] > PENDING_SECONDS:
        return None
    return entry


def merge_pending(sender, text):
    """Join a short follow-up onto the message we asked a location for."""
    if not sender or not text:
        return text, None
    with PENDING_LOCK:
        entry = PENDING.get(sender)
    if not entry or len(text) > 140:
        return text, None
    if time.time() - entry["asked_at"] > PENDING_SECONDS:
        return text, None
    with PENDING_LOCK:
        PENDING.pop(sender, None)
    joined = f"{entry['text']}\n\nThe resident then said where it is: {text}"
    return joined, entry


def take_pending_entry(sender):
    """Consume the pending entry: the location arrived another way."""
    with PENDING_LOCK:
        return PENDING.pop(sender, None)


def forget_report(report_id):
    """A pin confirmed on the map answered the question: stop waiting for a reply."""
    with PENDING_LOCK:
        for sender, entry in list(PENDING.items()):
            if entry.get("report_id") == report_id:
                PENDING.pop(sender, None)


# ---------------------------------------------------------------------------
# A pin shared before the words
# ---------------------------------------------------------------------------
def remember_place(sender, place):
    if not sender or not place:
        return
    with PLACES_LOCK:
        PLACES[sender] = {"place": place, "at": time.time()}
        while len(PLACES) > PLACE_LIMIT:
            PLACES.popitem(last=False)


def take_place(sender):
    """The pin the resident shared just before this message, if it is still fresh."""
    if not sender:
        return None
    with PLACES_LOCK:
        entry = PLACES.pop(sender, None)
    if not entry:
        return None
    if time.time() - entry["at"] > PLACE_SECONDS:
        return None
    return entry["place"]


# ---------------------------------------------------------------------------
# Where to reach a resident later
# ---------------------------------------------------------------------------
def remember_contact(reporter_ref, chat):
    if not reporter_ref or not chat:
        return
    with CONTACTS_LOCK:
        CONTACTS[reporter_ref] = chat
        CONTACTS.move_to_end(reporter_ref)
        while len(CONTACTS) > CONTACTS_LIMIT:
            CONTACTS.popitem(last=False)


def chat_for(reporter_ref):
    with CONTACTS_LOCK:
        return CONTACTS.get(reporter_ref)

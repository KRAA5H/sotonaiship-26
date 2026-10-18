"""One channel contract for the web app and the BlueBubbles webhook.

Both transports call `turn` with the same fields and the same `TurnRuntime`.
Only delivery differs: a browser renders bubbles, BlueBubbles sends them.
"""

import tools
from graph import service, store

ONBOARDING = "hey, this is soton council. what can we help with?"


def first_contact(sender):
    try:
        thread_id = tools.reporter_ref(sender or "") or "h-anon"
        return not store.ThreadStore().history(thread_id)
    except Exception:
        return False


def turn(sender, text="", photo_ref=None, image_ref=None, card=None,
         message_guid=None, chat=None):
    # Remember where to reach this resident. A confirmed map pin and a council status
    # change both text them later, and they find the chat here. Without it they have
    # nowhere to send, and the resident hears nothing after giving the street.
    from agents import memory
    memory.remember_contact(tools.reporter_ref(sender or ""), chat or sender)
    inbound = {
        "sender": sender or "",
        "chat": chat or sender or "",
        "text": text or "",
        "message_guid": message_guid or "",
        "photo_ref": photo_ref,
        "image_ref": image_ref,
        "card": card,
    }
    return service.get_runtime().turn(inbound)

"""BlueBubbles webhook receiver: the channel. The agents do the thinking.

MODE=triage : every message goes to the triage agent, the orchestrator of the
              multi-agent workflow in code/agents/ (plans/agents.md). It runs
              safety, location, photo, triage, category, duplicate, records and
              reply, and hands back one text.
MODE=echo   : one inbound text becomes one model call with no history, and one
              plain reply goes back out. No database write.
MODE=agent  : the original multi-turn IntakeAgent path, untouched.

What stays here is the channel itself, learned from real traffic:
  1. Return 200 immediately and reply from a background thread. BlueBubbles
     retries anything it thinks timed out, which produced duplicate replies.
  2. Deduplicate on the inbound message GUID.
  3. Coalesce a burst of quick messages into one turn, one turn per sender.
  4. Words first, the link as its own message.

The same server also serves the council site (/council, /r/<token>) and the
drop-a-pin map (/p/<token>), so SITE_URL is the one address residents need.

Run:
  python code/blue_bubbles.py
"""

import os
import re
import sys
import threading
import time
from collections import OrderedDict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv
from flask import Flask, jsonify, request

load_dotenv(Path(__file__).with_name(".env"))

import bb
import llm
import location  # noqa: F401  kept for callers that patch location.LocationService
import messages
import photos  # noqa: F401  registers /r/<token>/photo on the site blueprint
import pin_service
import rag  # noqa: F401  patched by tests; the agents use it
import reports_db  # noqa: F401  patched by tests; the agents use it
import tools  # noqa: F401  patched by tests; the agents use it
import triage  # noqa: F401
import voice  # noqa: F401  patched by tests; the agents use it
from agents import ORCHESTRATOR, Turn
from graph import service
from agents import memory
from agents.location_agent import is_location_card
from agents.triage_agent import (  # noqa: F401  the names this module has always offered
    NO_CONTENT,
    STILL_WORDS,
    URL_PATTERN,
    apply_place,
    is_question,
    wants_greeting,
    wants_silence,
    wants_status,
)
from geo import southampton as city
from website import site

MODE = (os.getenv("MODE") or "graph").lower()

# Never reply to the server's own account. Replying to yourself creates an
# infinite loop, because the reply itself arrives as a new inbound message.
IGNORE_SENDERS = {
    address.strip().lower()
    for address in (os.getenv("IGNORE_SENDERS") or "sidhari25@outlook.com").split(",")
    if address.strip()
}


def detect_self_address():
    """Probe BlueBubbles once at startup, never at import.

    Importing this module must not need the Mac: the simulator and the tests
    both import it without a running iMessage host.
    """
    try:
        detected = bb.self_address().strip().lower()
        if detected:
            IGNORE_SENDERS.add(detected)
    except Exception as error:  # noqa: BLE001
        print(f"[warn] could not read the server's own address: {error}")


# BlueBubbles replays recent messages when the server or the webhook restarts.
# Answering yesterday's messages on startup is worse than ignoring them.
STALE_SECONDS = int(os.getenv("STALE_SECONDS") or "120")

SYSTEM = (
    "You are the street report line for Southampton City Council. "
    "Reply in at most two short sentences, in plain English, with no jargon. "
    "If a photo is attached, say briefly what you can see and what happens next. "
    "If the photo is not a street or council issue, say so kindly and ask what they need. "
    "If you cannot tell what the photo shows, say so and ask where it is. "
    "Never give safety advice; if life is at risk, tell the person to call 999."
)

app = Flask(__name__)
# /council and /r/<token> on the same port, so SITE_URL links work.
app.register_blueprint(site)
# The drop-a-pin map too: /p/<token>, its /api/ and /static/ files.
pin_service.mount(app)

_sessions = {}
_agent = None
_seen = OrderedDict()
_seen_lock = threading.Lock()
SEEN_LIMIT = 500

# The agents' short-term memory, under the names this module has always used.
_pending = memory.PENDING
_pending_lock = memory.PENDING_LOCK
PENDING_SECONDS = memory.PENDING_SECONDS
PENDING_LIMIT = memory.PENDING_LIMIT
_places = memory.PLACES
PLACE_SECONDS = memory.PLACE_SECONDS
remember_location = memory.remember_location
merge_pending = memory.merge_pending
remember_place = memory.remember_place
take_place = memory.take_place

# The orchestrator's steps, under their old names.
reply_for = ORCHESTRATOR.act
status_reply = ORCHESTRATOR.status_reply
attach_photo_to_open_report = ORCHESTRATOR.attach_photo_to_open_report


def already_handled(message_guid):
    """True if this exact BlueBubbles message has been processed before."""
    if not message_guid:
        return False
    with _seen_lock:
        if message_guid in _seen:
            return True
        _seen[message_guid] = True
        while len(_seen) > SEEN_LIMIT:
            _seen.popitem(last=False)
    return False


def get_agent():
    global _agent
    if _agent is None:
        from conversational_ai import IntakeAgent

        _agent = IntakeAgent(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _agent


def _is_image_attachment(attachment):
    """Apple Maps pins and other plugin payloads are not photos."""
    name = (attachment.get("transferName") or "").lower()
    mime = (attachment.get("mimeType") or "").lower()
    if "plugin" in name:
        return False
    return mime.startswith("image/") or name.endswith(
        (".jpg", ".jpeg", ".png", ".heic", ".webp")
    )


def place_from_text(text):
    """A shared Apple or Google Maps pin, checked against the city boundary. None if absent."""
    return ORCHESTRATOR.location.shared_place(text)


BURST_SECONDS = float(os.getenv("BURST_SECONDS") or "2.5")

# iMessage arrives in bursts. One thought arrives as three short messages, and
# answering the first before the third lands is what makes a bot feel deaf.
# Wait for a quiet window, then treat the whole burst as one turn.
_burst = {}
_burst_lock = threading.Lock()

# One turn per sender at a time. A second message that lands while a turn is
# running is collected, never processed in parallel: two turns at once could
# save the same report twice and ask a question the resident already answered.
_inflight = set()
_inflight_lock = threading.Lock()


def _schedule(sender, entry):
    if entry.get("timer") is not None:
        return
    timer = threading.Timer(BURST_SECONDS, flush_burst, args=(sender,))
    timer.daemon = True
    entry["timer"] = timer
    timer.start()


def enqueue_message(inbound):
    """Buffer a message for its sender, resetting the quiet window."""
    sender = inbound.get("sender") or inbound.get("chat_guid")
    if not sender:
        return
    with _burst_lock:
        entry = _burst.setdefault(sender, {
            "texts": [], "attachments": [], "chat_guid": inbound.get("chat_guid"),
            "inbound": dict(inbound), "timer": None,
        })
        text = (inbound.get("text") or "").strip()
        if text:
            entry["texts"].append(text)
        entry["attachments"].extend(inbound.get("attachments") or [])
        entry["chat_guid"] = inbound.get("chat_guid")
        entry["inbound"] = dict(inbound)
        if sender not in _inflight:
            if entry["timer"] is not None:
                entry["timer"].cancel()
                entry["timer"] = None
            _schedule(sender, entry)


def flush_burst(sender):
    """Turn the quiet burst into one inbound message, one turn at a time."""
    with _inflight_lock:
        if sender in _inflight:
            return
        _inflight.add(sender)
    try:
        with _burst_lock:
            entry = _burst.pop(sender, None)
        if not entry:
            return
        inbound = dict(entry["inbound"])
        inbound["text"] = "\n".join(entry["texts"]).strip()
        inbound["attachments"] = entry["attachments"]
        if not inbound["text"] and not inbound["attachments"]:
            return
        if len(entry["texts"]) > 1:
            print(f"[burst] {len(entry['texts'])} messages from {sender} handled as one")
        handle_inbound(inbound)
    finally:
        with _inflight_lock:
            _inflight.discard(sender)
        # Anything that arrived during the turn gets its own quiet window now.
        with _burst_lock:
            entry = _burst.get(sender)
            if entry and (entry["texts"] or entry["attachments"]):
                if entry["timer"] is not None:
                    entry["timer"].cancel()
                    entry["timer"] = None
                _schedule(sender, entry)


def take_pending(sender):
    """Anything that arrived while we were thinking, folded into this turn."""
    with _burst_lock:
        entry = _burst.pop(sender, None)
    if not entry:
        return None
    if entry["timer"] is not None:
        entry["timer"].cancel()
    return entry


def _late_text(sender):
    """Words that arrived during the turn join it; a late photo gets its own turn next."""
    late = take_pending(sender)
    if not late:
        return None
    if late["attachments"]:
        print(f"[burst] a photo arrived late from {sender}, handling it next")
        enqueue_message({**late["inbound"], "text": "", "attachments": late["attachments"]})
    return "\n".join(late["texts"]).strip() or None


LINK_DELAY = float(os.getenv("LINK_DELAY") or "0.8")
LINK_LABELS = {"follow it", "details", "council page", "the council page", "form",
               "drop a pin", "your report"}


def split_reply(text):
    """Words first, link on its own line, the way a person texts."""
    text = (text or "").strip()
    match = URL_PATTERN.search(text)
    if not match:
        return text, ""
    link = match.group(0).rstrip(".,)")
    lines = []
    for line in (text[:match.start()] + "\n" + text[match.end():]).splitlines():
        cleaned = line.replace(link, "").rstrip(" :")
        if not cleaned.strip():
            continue
        if cleaned.strip().lower() in LINK_LABELS:
            continue
        lines.append(cleaned.strip())
    return "\n".join(lines).strip(), link


def deliver(chat_guid, text):
    """One text for the words, one for the link. Never one wall."""
    body, link = split_reply(text)
    if body:
        print(f"[send] words to {chat_guid}: {body[:90]}")
        bb.send_text(chat_guid, body)
    if link:
        time.sleep(LINK_DELAY)
        print(f"[send] link to {chat_guid}: {link[:70]}")
        bb.send_text(chat_guid, link)


# A pin confirmed on the map, or a status the council changed, reaches the
# resident here, on the chat they last used.
ORCHESTRATOR.set_notifier(deliver)


def read_attachments(attachments):
    """(image, photo_ref, card): the first photo, and a shared-location card's text.

    Only real images are downloaded for the photo agent. A maps plugin payload
    is never sent to a vision model, and a location card is read as text.
    """
    image, photo_ref, card = None, None, ""
    for attachment in attachments or []:
        if is_location_card(attachment):
            if not card:
                fetched = bb.download_attachment(attachment.get("guid"), width=None)
                if fetched:
                    card = fetched[0][:4096].decode("utf-8", "replace")
        elif image is None and _is_image_attachment(attachment):
            image = bb.download_attachment(attachment.get("guid"))
            if image:
                photo_ref = (attachment.get("guid"), attachment.get("mimeType") or image[1])
    return image, photo_ref, card


def _trace_line(outcome):
    return " | ".join(f"{step['agent']} {step['ms']}ms {step['note']}".strip()
                      for step in outcome.trace)


def handle_inbound(inbound):
    chat_guid = inbound["chat_guid"]
    text = inbound.get("text") or ""
    try:
        image, photo_ref, card = read_attachments(inbound.get("attachments") or [])

        if not text and not image and not card:
            bb.send_text(chat_guid, NO_CONTENT)
            return

        if MODE == "agent":
            from conversational_ai import ConversationSession

            sender = inbound.get("sender") or chat_guid
            session = _sessions.get(sender)
            if session is None or session.status != "open":
                session = ConversationSession(session_id=sender, phone_number=sender)
                _sessions[sender] = session
            result = get_agent().handle_message(session, text)
            deliver(chat_guid, result["reply_text"])
            return

        if MODE == "echo":
            # Plain chat with no database write: useful for testing the channel.
            reply, mode = llm.chat(
                SYSTEM, text or "The resident sent this photo with no words.", image, purpose="echo"
            )
            print(f"[reply] mode={mode} vision={bool(image)} to={chat_guid}: {reply[:120]}")
            deliver(chat_guid, reply)
            return

        if MODE == "graph":
            sender = inbound.get("sender") or chat_guid
            graph_inbound = {
                "sender": sender,
                "chat": chat_guid,
                "text": text,
                "message_guid": inbound.get("message_guid") or "",
                "photo_ref": photo_ref,
            }
            started = time.perf_counter()
            result = service.get_runtime().turn(graph_inbound)
            print(f"[graph] {round((time.perf_counter() - started) * 1000)}ms "
                  f"{result['kind']} to={chat_guid}")
            for bubble in result.get("bubbles") or []:
                deliver(chat_guid, bubble)
            if result.get("url"):
                deliver(chat_guid, result["url"])
            if result.get("source_url"):
                deliver(chat_guid, result["source_url"])
            return

        sender = inbound.get("sender") or chat_guid
        started = time.perf_counter()
        outcome = ORCHESTRATOR.handle(Turn(
            sender=sender, text=text, chat=chat_guid, image=image, photo_ref=photo_ref,
            card=card, late=lambda: _late_text(sender),
        ))
        print(f"[agents] {round((time.perf_counter() - started) * 1000)}ms {_trace_line(outcome)}")
        if not outcome.reply:
            print(f"[silent] nothing to send to {chat_guid}")
            return
        print(f"[reply] to={chat_guid}: {outcome.reply[:120]}")
        deliver(chat_guid, outcome.reply)
    except Exception as error:  # noqa: BLE001 - a webhook must never die silently
        print(f"[error] handling {chat_guid}: {error}")
        try:
            deliver(chat_guid, messages.sorry())
        except Exception as send_error:  # noqa: BLE001
            print(f"[error] fallback send failed: {send_error}")


@app.get("/health")
def health():
    deepseek = bool(os.getenv("DEEPSEEK_API_KEY"))
    return jsonify(
        {
            "ok": True,
            "mode": MODE,
            "orchestrator": "triage agent",
            "agents": ["safety", "triage", "photo", "category", "location", "duplicate",
                       "records", "reply", "status"],
            "text_provider": "deepseek" if deepseek else "openrouter",
            "text_model": llm.DS_MODEL,
            "thinking": "off",
            "vision_model": llm.DS_MODEL if deepseek else llm.VISION_MODEL,
            "vision_fallback": llm.VISION_MODEL,
            "city_boundary": city.in_city(50.9097, -1.4044) is not None,
            "streets": city.street_count(),
            "site_url": tools.SITE_URL,
            "bluebubbles": bb.BASE,
            "method": bb.METHOD,
            "handled": len(_seen),
        }
    )


@app.post("/webhook")
def webhook():
    payload = request.get_json(silent=True) or {}
    inbound = bb.normalise(payload)
    if not inbound or not inbound.get("chat_guid"):
        return jsonify({"ok": True, "action": "ignored"}), 200

    sender = (inbound.get("sender") or "").lower()
    chat_guid = (inbound.get("chat_guid") or "").lower()
    if sender in IGNORE_SENDERS or any(address in chat_guid for address in IGNORE_SENDERS):
        print(f"[skip] own account, not replying: sender={sender} chat={chat_guid}")
        return jsonify({"ok": True, "action": "ignored_self"}), 200

    created = inbound.get("date_created")
    if isinstance(created, (int, float)) and created > 0:
        created_seconds = created / 1000 if created > 1e12 else created
        if time.time() - created_seconds > STALE_SECONDS:
            print(f"[skip] stale message from {sender}, {int(time.time() - created_seconds)}s old")
            return jsonify({"ok": True, "action": "ignored_stale"}), 200

    if already_handled(inbound.get("message_guid")):
        return jsonify({"ok": True, "action": "duplicate"}), 200

    print(
        f"[inbound] from={inbound.get('sender')} chat={inbound['chat_guid']} "
        f"text={inbound.get('text', '')[:120]!r} "
        f"attachments={len(inbound.get('attachments') or [])}"
    )
    enqueue_message(inbound)
    return jsonify({"ok": True, "action": "accepted"}), 200


if __name__ == "__main__":
    detect_self_address()
    app.run(host="0.0.0.0", port=5005, threaded=True)

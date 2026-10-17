"""BlueBubbles webhook receiver.

MODE=echo  : one inbound text becomes one model call with no history, and one
             reply goes back out.
MODE=agent : the original multi-turn IntakeAgent path, untouched.

Two operational rules, both learned from real traffic:
  1. Return 200 immediately and reply from a background thread. A model call
     takes 4 to 11 seconds, and BlueBubbles retries anything it thinks timed
     out, which produced duplicate replies.
  2. Deduplicate on the inbound message GUID. A retry of the same message must
     never be answered twice or billed twice.

Run:
  python code/blue_bubbles.py
"""

import os
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

MODE = (os.getenv("MODE") or "echo").lower()

# Never reply to the server's own account. Replying to yourself creates an
# infinite loop, because the reply itself arrives as a new inbound message.
IGNORE_SENDERS = {
    address.strip().lower()
    for address in (os.getenv("IGNORE_SENDERS") or "sidhari25@outlook.com").split(",")
    if address.strip()
}
try:
    _detected = bb.self_address().strip().lower()
    if _detected:
        IGNORE_SENDERS.add(_detected)
except Exception as _error:  # noqa: BLE001
    print(f"[warn] could not read the server's own address: {_error}")

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

_sessions = {}
_agent = None
_seen = OrderedDict()
_seen_lock = threading.Lock()
SEEN_LIMIT = 500


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


def handle_inbound(inbound):
    chat_guid = inbound["chat_guid"]
    text = inbound.get("text") or ""
    try:
        image = None
        attachments = inbound.get("attachments") or []
        if attachments:
            image = bb.download_attachment(attachments[0].get("guid"))

        if not text and not image:
            bb.send_text(
                chat_guid,
                "I can only read text and photos just now. Please describe the problem in a few words.",
            )
            return

        if MODE == "agent":
            from conversational_ai import ConversationSession

            sender = inbound.get("sender") or chat_guid
            session = _sessions.get(sender)
            if session is None or session.status != "open":
                session = ConversationSession(session_id=sender, phone_number=sender)
                _sessions[sender] = session
            result = get_agent().handle_message(session, text)
            bb.send_text(chat_guid, result["reply_text"])
            return

        prompt = text or "The resident sent this photo with no words."
        reply, mode = llm.chat(SYSTEM, prompt, image)
        print(f"[reply] mode={mode} vision={bool(image)} to={chat_guid}: {reply[:120]}")
        bb.send_text(chat_guid, reply)
    except Exception as error:  # noqa: BLE001 - a webhook must never die silently
        print(f"[error] handling {chat_guid}: {error}")
        try:
            bb.send_text(chat_guid, llm.STUB_REPLY)
        except Exception as send_error:  # noqa: BLE001
            print(f"[error] fallback send failed: {send_error}")


@app.get("/health")
def health():
    return jsonify(
        {
            "ok": True,
            "mode": MODE,
            "text_provider": "deepseek" if os.getenv("DEEPSEEK_API_KEY") else "openrouter",
            "text_model": llm.DS_MODEL,
            "vision_model": llm.VISION_MODEL,
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
    threading.Thread(target=handle_inbound, args=(inbound,), daemon=True).start()
    return jsonify({"ok": True, "action": "accepted"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5005, threaded=True)

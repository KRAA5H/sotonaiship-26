"""BlueBubbles webhook receiver.

MODE=echo  : one inbound text becomes one model call with no history, and one
             reply goes back out. This is the current stage.
MODE=agent : the original multi-turn IntakeAgent path, untouched.

Run:
  python code/blue_bubbles.py
  MODE=echo python code/blue_bubbles.py
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv
from flask import Flask, jsonify, request

load_dotenv(Path(__file__).with_name(".env"))

import bb
import llm

MODE = (os.getenv("MODE") or "echo").lower()

SYSTEM = (
    "You are the street report line for Southampton City Council. "
    "Reply in at most two short sentences, in plain English, with no jargon. "
    "Never give safety advice; if life is at risk, tell the person to call 999."
)

app = Flask(__name__)

# Agent mode keeps the original multi-turn behaviour. It is built lazily so
# echo mode works with no Anthropic key present.
_sessions = {}
_agent = None


def get_agent():
    global _agent
    if _agent is None:
        from conversational_ai import IntakeAgent

        _agent = IntakeAgent(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _agent


@app.get("/health")
def health():
    return jsonify(
        {
            "ok": True,
            "mode": MODE,
            "llm_model": llm.MODEL,
            "bluebubbles": bb.BASE,
            "method": bb.METHOD,
        }
    )


@app.post("/webhook")
def webhook():
    payload = request.get_json(silent=True) or {}
    inbound = bb.normalise(payload)
    if not inbound or not inbound.get("chat_guid"):
        return jsonify({"ok": True, "action": "ignored"}), 200

    chat_guid = inbound["chat_guid"]
    text = inbound.get("text") or ""

    if not text:
        bb.send_text(
            chat_guid,
            "I can only read text just now. Please describe the problem in a few words.",
        )
        return jsonify({"ok": True, "action": "asked"}), 200

    if MODE == "agent":
        from conversational_ai import ConversationSession

        sender = inbound.get("sender") or chat_guid
        session = _sessions.get(sender)
        if session is None or session.status != "open":
            session = ConversationSession(session_id=sender, phone_number=sender)
            _sessions[sender] = session
        result = get_agent().handle_message(session, text)
        bb.send_text(chat_guid, result["reply_text"])
        return jsonify({"ok": True, "action": result["status"]}), 200

    reply, mode = llm.chat(SYSTEM, text)
    sent, _body = bb.send_text(chat_guid, reply)
    return jsonify({"ok": True, "action": "replied", "mode": mode, "sent": sent}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5005)

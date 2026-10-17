import os
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv

from conversational_ai import ConversationSession, IntakeAgent

load_dotenv()

app = Flask(__name__)
agent = IntakeAgent(api_key=os.getenv("ANTHROPIC_API_KEY"))

BB_URL = os.getenv("BLUEBUBBLES_SERVER_URL")
BB_PASSWORD = os.getenv("BLUEBUBBLES_PASSWORD")

# One ConversationSession per sender, kept in memory for the demo.
# A real version would persist these via Sector 3's database instead,
# so a conversation survives a restart.
active_sessions: dict[str, ConversationSession] = {}


def send_reply(chat_guid: str, text: str):
    """Sends a text back out through BlueBubbles to the original sender."""
    url = f"{BB_URL}/api/v1/message/text?password={BB_PASSWORD}"
    payload = {"chatGuid": chat_guid, "message": text, "method": "private-api"}
    requests.post(url, json=payload, timeout=10)


@app.route("/webhook", methods=["POST"])
def webhook():
    """BlueBubbles calls this every time a new message arrives.

    IMPORTANT: BlueBubbles' exact payload field names can differ slightly
    by version. Print `data` the first time you test this and adjust the
    field lookups below to match what you actually see - don't assume
    this shape is 100% correct without checking against your own server.
    """
    data = request.json
    print("Raw webhook payload:", data)  # keep this while testing, remove later

    if data.get("type") != "new-message":
        return jsonify({"status": "ignored"})

    message = data["data"]
    sender = message["handle"]["address"]  # the phone number / contact
    chat_guid = message["chats"][0]["guid"]  # where to send the reply back
    text = message.get("text", "")

    # Get or start this sender's session - this is what makes it a real
    # multi-turn conversation instead of treating every text as brand new.
    session = active_sessions.get(sender)
    if session is None or session.status != "open":
        session = ConversationSession(session_id=sender, phone_number=sender)
        active_sessions[sender] = session

    result = agent.handle_message(session, text)
    send_reply(chat_guid, result["reply_text"])

    if result["status"] in ("complete", "incomplete"):
        print(f"Session for {sender} finished: {result['summary']}")
        # This is the handoff point - pass result["summary"] / session
        # into Sector 2 (classification) here once that's wired up.

    return jsonify({"status": "handled"})


if __name__ == "__main__":
    app.run(port=5005)

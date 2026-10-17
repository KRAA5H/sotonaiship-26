import os
import json
import base64
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv()

MAX_EXCHANGES = 5  # hard cap - after this many messages, force completion


# ---------------------------------------------------------------------------
# 1. THE DATA: a session holds everything about one resident's conversation.
#    Nothing here is AI - it's just state, same as PaymentRequest or
#    StreetReport in the other sectors.
# ---------------------------------------------------------------------------
@dataclass
class ConversationSession:
    session_id: str
    phone_number: str              # synthetic for the demo, never a real number
    messages: list = field(default_factory=list)   # Claude-format message history
    status: str = "open"           # "open" | "complete" | "incomplete"
    exchange_count: int = 0
    summary: Optional[dict] = None  # filled in once status leaves "open"

    def add_user_message(self, text: str, photo_path: Optional[str] = None):
        """Appends a resident message to the history. Handles an optional
        photo the same way the other sectors do: base64-encode it, add it
        as a second content block alongside the text."""
        content = [{"type": "text", "text": text}]

        if photo_path and os.path.exists(photo_path):
            with open(photo_path, "rb") as f:
                image_b64 = base64.standard_b64encode(f.read()).decode("utf-8")
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64},
            })

        self.messages.append({"role": "user", "content": content})

    def add_assistant_message(self, text: str):
        self.messages.append({"role": "assistant", "content": text})


# ---------------------------------------------------------------------------
# 2. THE AGENT: one method, handle_message(), called once per resident
#    message. It sends the WHOLE conversation so far to Claude each time -
#    that's the one genuinely new pattern here versus a single-shot call.
#
#    IMPORTANT CHANGE: this agent no longer asks for location itself.
#    Every resident now goes through a mandatory location link (see
#    location.py + blue_bubbles.py's /locate routes) BEFORE this agent is
#    ever called - by the time handle_message() runs, street_name,
#    postcode and area are already known and stored separately. The old
#    prompt asked the agent to collect "the location" conversationally,
#    which is now both redundant and wrong, since the resident was never
#    going to type it themselves. The synthetic "[Location shared via
#    link: ...]" message blue_bubbles.py inserts after the link flow is
#    purely informational context for the agent, not something it needs
#    to request.
# ---------------------------------------------------------------------------
class IntakeAgent:
    SYSTEM_PROMPT = """You are an intake assistant for Southampton City Council's
street report line. Your only job: collect enough information about a
resident's issue (pothole, fly-tipping, broken streetlight, graffiti,
flooding, or other) to hand it off for classification. You need:
- a description of the problem
- a photo, if the resident can provide one (not mandatory)

Do NOT ask the resident for their location. Location is always collected
separately, before you are involved, and will appear in the conversation
as a system note such as "[Location shared via link: Shirley High Street,
SO15 5LF]" - treat that as already-known fact, never ask for it again.

Ask ONE clarifying question at a time if something important is missing.
Once you have a workable description (and a photo, if one is coming),
mark the report complete - don't keep asking once you have enough.

Respond with ONLY valid JSON, no other text, in this exact shape:
{"status": "ask_more" | "complete",
 "reply_text": "what to say back to the resident",
 "summary": {"description": "...", "has_photo": true|false}}

If status is "ask_more", summary can be null.
"""

    def __init__(self, api_key: str):
        self.client = Anthropic(api_key=api_key)

    def handle_message(self, session: ConversationSession, incoming_text: str,
                        photo_path: Optional[str] = None) -> dict:
        """Call this once per incoming resident message. Updates the session
        in place and returns the agent's structured decision."""

        session.add_user_message(incoming_text, photo_path)
        session.exchange_count += 1

        # --- THE CAP: check this BEFORE calling the AI, so a resident who
        # never gives a straight answer can't run up your API bill or loop
        # forever waiting for a "complete" that never comes. ---
        if session.exchange_count >= MAX_EXCHANGES and session.status == "open":
            session.status = "incomplete"
            session.summary = {
                "description": incoming_text,
                "has_photo": photo_path is not None,
            }
            reply = ("Thanks - we've logged what you've shared so far. "
                     "A council officer will follow up if more detail is needed.")
            session.add_assistant_message(reply)
            return {"status": "incomplete", "reply_text": reply, "summary": session.summary}

        # --- THE ACTUAL CALL: note messages=session.messages, not just the
        # latest one. This is what makes it a conversation instead of a
        # series of unrelated single questions. ---
        response = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=400,
            system=self.SYSTEM_PROMPT,
            messages=session.messages,
        )

        raw_text = response.content[0].text
        cleaned = raw_text.replace("```json", "").replace("```", "").strip()

        try:
            result = json.loads(cleaned)
        except json.JSONDecodeError:
            # Never let a parsing hiccup break the conversation for the
            # resident - fall back to asking again rather than crashing.
            result = {
                "status": "ask_more",
                "reply_text": "Sorry, could you tell me a bit more about the issue?",
                "summary": None,
            }

        session.add_assistant_message(result["reply_text"])

        if result["status"] == "complete":
            session.status = "complete"
            session.summary = result["summary"]

        return result


# ---------------------------------------------------------------------------
# DEMO: simulates a short, realistic back-and-forth, including the
# synthetic location note the real pipeline inserts after the link flow.
# Run this file directly.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    agent = IntakeAgent(api_key=os.getenv("ANTHROPIC_API_KEY"))
    session = ConversationSession(session_id="demo-1", phone_number="+44-SYNTHETIC-001")

    # In the real pipeline, blue_bubbles.py sends the location-shared
    # message AFTER the link flow completes - simulated here as the first
    # turn, same as it would arrive for real.
    resident_messages = [
        "[Location shared via link: Shirley High Street, SO15 5LF]",
        "There's a massive pothole outside my house",
    ]

    for message in resident_messages:
        result = agent.handle_message(session, message)
        print(f"\nResident: {message}")
        print(f"Agent: {json.dumps(result, indent=2)}")
        if result["status"] in ("complete", "incomplete"):
            break

    print(f"\nFinal session status: {session.status}")
    print(f"Summary: {session.summary}")

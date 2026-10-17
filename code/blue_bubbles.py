"""BlueBubbles webhook receiver.

MODE=triage : one inbound message is classified, saved as a report when it is a
              council matter, and the resident gets a link to their own page.
MODE=echo   : one inbound text becomes one model call with no history, and one
              plain reply goes back out. No database write.
MODE=agent  : the original multi-turn IntakeAgent path, untouched.

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
import re
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from collections import OrderedDict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv
from flask import Flask, jsonify, request

load_dotenv(Path(__file__).with_name(".env"))

import bb
import llm
import messages
import rag
import reports_db
import photos  # noqa: F401  registers /r/<token>/photo on the site blueprint
import tools
import triage
import voice
from website import site

MODE = (os.getenv("MODE") or "triage").lower()

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
# /council and /r/<token> on the same port, so SITE_URL links work.
app.register_blueprint(site)

_sessions = {}
_agent = None
_seen = OrderedDict()
_seen_lock = threading.Lock()
SEEN_LIMIT = 500

# When we ask "where is it?" the next short message from that person is their
# answer, not a new report. Remember the first half so the two join up.
_pending = OrderedDict()
_pending_lock = threading.Lock()
PENDING_SECONDS = 600
PENDING_LIMIT = 200


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


def merge_pending(sender, text):
    """Join a short follow-up onto the message we asked a location for."""
    if not sender or not text:
        return text, None
    with _pending_lock:
        entry = _pending.get(sender)
    if not entry or len(text) > 140:
        return text, None
    if time.time() - entry["asked_at"] > PENDING_SECONDS:
        return text, None
    with _pending_lock:
        _pending.pop(sender, None)
    joined = f"{entry['text']}\n\nThe resident then said where it is: {text}"
    return joined, entry


def remember_location(sender, text, saved, decision):
    """Hold the incomplete report, so the answer becomes its street, not a new row."""
    if not sender or not text:
        return
    with _pending_lock:
        _pending[sender] = {
            "text": text,
            "asked_at": time.time(),
            "report_id": saved["report_id"],
            "link": saved["link"],
            "category_id": decision["category_id"],
            "has_photo": bool(decision.get("has_photo")),
        }
        while len(_pending) > PENDING_LIMIT:
            _pending.popitem(last=False)


def _voice_facts(decision, saved=None, **extra):
    """The facts the voice layer may use. The link is appended by voice.say."""
    facts = {
        "category_id": decision.get("category_id"),
        "category_label": decision.get("category_label"),
        "location": decision.get("location"),
        "has_photo": bool(decision.get("has_photo")),
    }
    if saved and saved.get("link"):
        facts["link"] = saved["link"]
    facts.update({key: value for key, value in extra.items() if value})
    return facts


def _is_image_attachment(attachment):
    """Apple Maps pins and other plugin payloads are not photos."""
    name = (attachment.get("transferName") or "").lower()
    mime = (attachment.get("mimeType") or "").lower()
    if "plugin" in name:
        return False
    return mime.startswith("image/") or name.endswith(
        (".jpg", ".jpeg", ".png", ".heic", ".webp")
    )


def attach_photo_to_open_report(sender, attachment, image):
    """Attach a late photo to the one open report that needs one."""
    guid = (attachment or {}).get("guid")
    if not guid or not sender:
        return None
    mime = (attachment.get("mimeType") or (image[1] if image else "") or "").strip()

    pending = _pending.get(sender) or {}
    if pending.get("report_id") and pending.get("link"):
        report_id, link = pending["report_id"], pending["link"]
    else:
        reference = tools.reporter_ref(sender)
        rows = _with_db(lambda c: reports_db.open_reports_for(c, reference))
        cutoff = datetime.now(timezone.utc) - timedelta(hours=72)
        fresh = []
        for row in rows or []:
            try:
                created = datetime.fromisoformat(str(row.get("created_at")))
            except (TypeError, ValueError):
                continue
            if created >= cutoff:
                fresh.append(row)
        # One report, or we ask which one. Never guess.
        if len(fresh) != 1:
            return None
        report_id = fresh[0]["id"]
        link = f"{tools.SITE_URL}/r/{fresh[0]['link_token']}"

    if not _with_db(lambda c: reports_db.set_photo(c, report_id, guid, mime)):
        return None
    print(f"[photo] attached {guid[:8]} to {report_id}")
    return {"report_id": report_id, "link": link}


def reply_for(decision, sender, text="", has_photo=False, pending=None, relink_to=None,
              photo=None):
    """Save what triage accepted, and return the one text the resident gets back."""
    decision = dict(decision)
    decision["has_photo"] = bool(has_photo)
    reason = decision["reason"]

    # The resident answered our question about where it is: fill that report in.
    if (reason == "ok" and pending and pending.get("report_id")
            and decision["category_id"] == pending.get("category_id")):
        if _with_db(lambda c: reports_db.set_location(
                c, pending["report_id"], decision["location"])):
            print(f"[located] {pending['report_id']} -> {decision['location']}")
            decision["has_photo"] = bool(pending.get("has_photo",
                                                     decision.get("has_photo")))
            template = messages.logged(decision, {"link": pending["link"]})
            return voice.say("saved", _voice_facts(decision, link=pending["link"]), template)

    if reason == "ok":
        saved = tools.save_report(
            category_id=decision["category_id"],
            location=decision["location"],
            description=decision["description"],
            severity=decision["severity"],
            has_photo=has_photo,
            reporter=sender,
        )
        if not saved.get("ok"):
            print(f"[save] refused: {saved.get('error')}")
            return voice.say("incomplete", _voice_facts(decision),
                             messages.need_location(decision))

        print(f"[saved] {saved['report_id']} {decision['category_id']} "
              f"sev={decision['severity']} duplicate_of={saved['duplicate_of']}")

        if photo and photo[0]:
            _with_db(lambda c: reports_db.set_photo(
                c, saved["report_id"], photo[0], photo[1]))

        if saved.get("duplicate_of"):
            template = messages.duplicate(decision, saved)
            return voice.say("duplicate", _voice_facts(decision, saved), template)

        if relink_to:
            _with_db(lambda c: reports_db.link_duplicate(c, saved["report_id"], relink_to))
            print(f"[relink] {saved['report_id']} -> {relink_to}")

        template = messages.logged(decision, saved)
        return voice.say("saved", _voice_facts(decision, saved), template)

    if reason == "no_location":
        # Act first: keep the report, then ask for the one thing only they know.
        saved = tools.save_report(
            category_id=decision["category_id"],
            location="Not given",
            description=decision["description"],
            severity=decision["severity"],
            has_photo=has_photo,
            reporter=sender,
        )
        if saved.get("ok"):
            remember_location(sender, text, saved, decision)
            if photo and photo[0]:
                _with_db(lambda c: reports_db.set_photo(
                    c, saved["report_id"], photo[0], photo[1]))
            print(f"[saved] {saved['report_id']} {decision['category_id']} "
                  "incomplete, waiting for the street")
        else:
            print(f"[save] refused: {saved.get('error')}")
        return voice.say("incomplete", _voice_facts(decision),
                         messages.need_location(decision))

    if reason == "emergency":
        # Safety wording is never model-written.
        return messages.emergency()

    if reason.startswith("no_report_for_") or reason == "model_says_not_a_report":
        if has_photo and decision["description"]:
            seen = re.sub(r"^(the )?(photo|image) (shows|showing|is of)\s+", "",
                          decision["description"].strip(), flags=re.IGNORECASE).rstrip(".")
            return (f"From your photo: {seen}. That is not something the council "
                    "can act on, so nothing has been logged.")

        contact = messages.contact_for(decision.get("category_id"))
        is_not_council = (decision.get("outcome") == "not_council" or
                          str(decision.get("category_id") or "").startswith("not_council"))
        if is_not_council:
            facts = _voice_facts(
                decision,
                link=contact.get("page"),
                link_label="Details",
                org=contact.get("org"),
                contact=contact.get("contact"),
            )
            return voice.say("not_council", facts, messages.not_council(decision))

        if is_question(text):
            grounded, _ = rag.answer(text, decision.get("category_id"))
            if grounded:
                return messages.answered(grounded)

        page = messages.contact_for(decision.get("category_id")).get("page") \
            or messages.COUNCIL_CONTACT
        facts = _voice_facts(decision, link=page, link_label="The council page",
                             page=page)
        return voice.say("no_answer", facts, messages.no_answer(decision))

    return voice.say("unclear", _voice_facts(decision), messages.unclear())


STATUS_WORDS = re.compile(
    r"\b(any )?updates?\b|\bstatus\b|\bany news\b|\bwhat'?s happening\b|"
    r"\bis (it|this) (fixed|done)\b|\bheard (anything|back)\b|\bprogress\b",
    re.IGNORECASE,
)
STILL_WORDS = re.compile(
    r"still (there|not fixed|not done|broken|a problem)|not (been )?fixed|"
    r"no ?one (came|fixed)|nobody (came|fixed)",
    re.IGNORECASE,
)
SILENCE_WORDS = re.compile(
    r"^(thanks|thank you|cheers|ta|ok|okay|cool|got it|perfect|great|nice one)[\s!.,]*$",
    re.IGNORECASE,
)
GREETING_WORDS = re.compile(
    r"^(hi|hello|hey|hiya|good (morning|afternoon|evening))( there)?[\s!.,]*$",
    re.IGNORECASE,
)
QUESTION_WORDS = re.compile(
    r"^(how|what|when|where|who|why|can|could|do|does|is|are|will|should)\b",
    re.IGNORECASE,
)


def _with_db(work):
    """One short-lived connection, always closed."""
    conn = reports_db.connect()
    try:
        return work(conn)
    finally:
        conn.close()


def wants_status(text):
    """True for a short question about the report they already made."""
    return bool(text) and len(text) <= 120 and bool(STATUS_WORDS.search(text))


def wants_silence(text):
    """A thank you or an acknowledgement. Answering it would be noise."""
    return bool(text) and len(text) <= 25 and bool(SILENCE_WORDS.search(text))


def wants_greeting(text):
    return bool(text) and len(text) <= 25 and bool(GREETING_WORDS.search(text))


def is_question(text):
    text = (text or "").strip()
    return text.endswith("?") or bool(QUESTION_WORDS.search(text))


def status_reply(sender):
    """Answer from the database, not the model. None when there is nothing to say."""
    report = _with_db(lambda c: reports_db.latest_report_for(c, tools.reporter_ref(sender)))
    if not report:
        return None
    report["link"] = f"{tools.SITE_URL}/r/{report['link_token']}"
    report["status_text"] = tools.STATUS_TEXT.get(report["status"], report["status"])
    facts = {
        "category_id": report["category_id"],
        "location": report["location"],
        "status_text": report["status_text"],
        "link": report["link"],
    }
    return report, voice.say("status", facts, messages.status(report))


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

        if MODE == "echo":
            # Plain chat with no database write: useful for testing the channel.
            reply, mode = llm.chat(
                SYSTEM, text or "The resident sent this photo with no words.", image
            )
            print(f"[reply] mode={mode} vision={bool(image)} to={chat_guid}: {reply[:120]}")
            bb.send_text(chat_guid, reply)
            return

        sender = inbound.get("sender") or chat_guid
        if wants_silence(text):
            print(f"[silent] acknowledgement from {sender}")
            return
        if wants_greeting(text):
            print(f"[greeting] {sender}")
            bb.send_text(chat_guid, voice.say("greeting", {}, messages.greeting()))
            return
        relink_to = None
        if wants_status(text):
            found = status_reply(sender)
            if found:
                report, status_text = found
                if report["status"] != "resolved" or not STILL_WORDS.search(text):
                    print(f"[status] {report['id']} -> {report['status']}")
                    bb.send_text(chat_guid, status_text)
                    return
                relink_to = report["id"]
        if image and not text and attachments and _is_image_attachment(attachments[0]):
            if sender not in _pending:
                candidates = _with_db(
                    lambda c: reports_db.open_reports_for(c, tools.reporter_ref(sender))) or []
                cutoff = datetime.now(timezone.utc) - timedelta(hours=72)
                fresh = []
                for row in candidates:
                    try:
                        created = datetime.fromisoformat(str(row.get("created_at")))
                    except (TypeError, ValueError):
                        continue
                    if created >= cutoff:
                        fresh.append(row)
                if len(fresh) > 1:
                    print(f"[photo] {len(fresh)} open reports for {sender}, asking which")
                    bb.send_text(chat_guid, messages.which_report(fresh))
                    return
            attached = attach_photo_to_open_report(sender, attachments[0], image)
            if attached:
                facts = {"link": attached["link"], "link_label": "Your report"}
                reply = voice.say("photo_added", facts,
                                  messages.photo_added(attached["link"]))
                print(f"[reply] to={chat_guid}: {reply[:120]}")
                bb.send_text(chat_guid, reply)
                return

        text, pending = merge_pending(sender, text)
        if pending:
            print(f"[pending] joined a follow-up from {sender}")
        decision = triage.triage(text, image)
        late = take_pending(sender)
        if late and late["texts"]:
            extra = "\n".join(late["texts"]).strip()
            if extra:
                text = f"{text}\n{extra}".strip()
                print(f"[burst] folded a late message from {sender} into this turn")
                decision = triage.triage(text, image)
        late_photo = take_pending(sender)
        if late_photo and late_photo["attachments"] and not late_photo["texts"]:
            print(f"[burst] a photo arrived late from {sender}, handling it next")
            enqueue_message({**late_photo["inbound"], "text": "",
                             "attachments": late_photo["attachments"]})
        print(f"[triage] report={decision['is_report']} {decision['category_id']} "
              f"sev={decision['severity']} conf={decision['confidence']} "
              f"why={decision['reason']} to={chat_guid}")
        photo = None
        if image and attachments and _is_image_attachment(attachments[0]):
            photo = (attachments[0].get("guid"),
                     attachments[0].get("mimeType") or image[1])
        reply = reply_for(decision, sender, text, bool(image), pending, relink_to, photo)
        if not reply:
            print(f"[silent] nothing to send to {chat_guid}")
            return
        print(f"[reply] to={chat_guid}: {reply[:120]}")
        bb.send_text(chat_guid, reply)
    except Exception as error:  # noqa: BLE001 - a webhook must never die silently
        print(f"[error] handling {chat_guid}: {error}")
        try:
            bb.send_text(chat_guid, messages.sorry())
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
            "vision_model": llm.DS_MODEL if os.getenv("DEEPSEEK_API_KEY")
                            else llm.VISION_MODEL,
            "vision_fallback": llm.VISION_MODEL,
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
    app.run(host="0.0.0.0", port=5005, threaded=True)

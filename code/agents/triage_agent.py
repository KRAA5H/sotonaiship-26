"""Triage agent: the orchestrator. Every inbound message goes through here.

It keeps the turn's state and calls the other agents in order (plans/agents.md):

  1 Safety     rules first: 999 before anything else, threats and spam stopped
    (cheap)    thanks, hello and "any update?" answered with no model call
  5 Location   a shared pin or location card; a short reply to "which street?"
               answered offline, with no model call
  3 Photo      started in parallel the moment a photo arrives
  2 Triage     the ONE model call on the happy path (DeepSeek, thinking off)
  1 Safety     second net on what triage found
  5 Location   tidies the street, never calls a city street "outside"
  4 Category   the specialist for that category: severity, location mode,
               handoff to the council form for neighbour problems
  6 Duplicate  same person twice: nothing new saved; someone else: linked
  7 Records    saves, fills in the street, photo and photo features
  5 Location   no street yet: a map link, "reply with the street" or "share
               your location"
  8 Reply      writes the text from the facts (one model call, template fallback)
  9 Status     separate path: the council changes a status, the resident is told

Only triage, photo and reply call a model. Everything else is code.
handle(turn) returns an Outcome: the reply (or None for silence), the
decision, and a trace of which agent did what and how long it took.
"""

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import messages
import pin_service
import rag
import reports_db
import tools
import triage
import voice
import website

from . import memory
from .categories import agent_for
from .duplicate import DuplicateAgent
from .location_agent import LocationAgent
from .photo import POOL, PhotoAgent
from .records import RecordsAgent, with_db
from .reply import ReplyAgent
from .safety import SafetyAgent
from .status import StatusAgent

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
URL_PATTERN = re.compile(r"https?://\S+")
NO_CONTENT = "I can only read text and photos just now. Please describe the problem in a few words."
LATE_PHOTO_HOURS = 72


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


def apply_place(decision, place):
    """A pin is a location. Use it instead of asking for one."""
    if not place or not place.get("street_name"):
        return decision
    decision = dict(decision)
    if decision.get("location"):
        return decision
    if decision.get("outcome") != "council_report":
        return decision
    decision["location"] = place["street_name"]
    if place.get("area"):
        decision["area"] = place["area"]
    if decision.get("reason") in ("no_location", "model_says_not_a_report"):
        decision["reason"] = "ok"
        decision["is_report"] = True
    return decision


@dataclass
class Turn:
    """One message, as the orchestrator sees it. No phone number beyond the sender key."""
    sender: str
    text: str = ""
    chat: str = ""                     # where to reply; kept only in short-term memory
    image: tuple = None                # (bytes, mime) of a photo
    photo_ref: tuple = None            # (attachment guid, mime), to attach the photo
    card: str = ""                     # text of a shared-location card
    late: object = None                # callable: text that arrived while we were busy
    link_base: str = None              # base URL for the map link (the simulator's host)


@dataclass
class Outcome:
    reply: object                      # the text to send, or None for silence
    decision: dict = None
    trace: list = field(default_factory=list)


class TriageAgent:
    """The orchestrator. Owns the turn; the other agents are its specialists."""
    name = "triage"

    def __init__(self):
        self.safety = SafetyAgent()
        self.photo = PhotoAgent()
        self.location = LocationAgent()
        self.duplicate = DuplicateAgent()
        self.records = RecordsAgent()
        self.reply = ReplyAgent()
        self.status = StatusAgent(self.records, self.reply)
        self.notify = None             # notify(chat, text): set by the channel
        # The map page and the dashboard call back into the agents.
        pin_service.HOOKS["on_confirm"] = self.on_pin_confirmed
        pin_service.HOOKS["describe"] = self.describe_report
        if self.status.on_status_change not in website.STATUS_HOOKS:
            website.STATUS_HOOKS.append(self.status.on_status_change)

    def set_notifier(self, notify):
        """How a later text (pin confirmed, status changed) reaches the resident."""
        self.notify = notify
        self.status.notify = notify

    # ------------------------------------------------------------------------
    # The turn
    # ------------------------------------------------------------------------
    def handle(self, turn):
        trace = []

        def step(agent, started, note=""):
            trace.append({"agent": agent, "ms": round((time.perf_counter() - started) * 1000),
                          "note": note})

        sender = turn.sender
        text = (turn.text or "").strip()
        if turn.chat:
            memory.remember_contact(tools.reporter_ref(sender), turn.chat)
        if not text and not turn.image and not turn.card:
            return Outcome(NO_CONTENT, {"reason": "empty"}, trace)

        # 1. Safety: always first, never reworded.
        started = time.perf_counter()
        stop = self.safety.check(text)
        step("safety", started, stop["kind"] if stop else "clear")
        if stop:
            return Outcome(stop["reply"], {"reason": stop["kind"]}, trace)

        # Cheap turns: no model call at all.
        if wants_silence(text):
            return Outcome(None, {"reason": "silence"}, trace)
        if wants_greeting(text):
            return Outcome(self.reply.say("greeting", {}, messages.greeting()), {"reason": "greeting"}, trace)
        relink_to = None
        if wants_status(text):
            found = self.status_reply(sender)
            if found:
                report, status_text = found
                if report["status"] != "resolved" or not STILL_WORDS.search(text):
                    print(f"[status] {report['id']} -> {report['status']}")
                    return Outcome(status_text, {"reason": "status"}, trace)
                relink_to = report["id"]

        # A photo with no words, for a report that is already open.
        if turn.image and not text and turn.photo_ref:
            reply = self.late_photo(sender, turn.photo_ref, turn.image)
            if reply is not None:
                return Outcome(reply, {"reason": "photo_added"}, trace)

        # 5. Location: a pin or location card in this message.
        started = time.perf_counter()
        place = self.location.shared_place(text, turn.card)
        if place:
            rest = URL_PATTERN.sub("", text).strip(" ,-\n")
            if not place["in_city"]:
                step("location", started, "shared pin outside the city")
                return Outcome(messages.pin_outside(place), {"reason": "outside"}, trace)
            pending = memory.pending_for(sender)
            if pending and not rest:
                reply = self.fill_pending(pending, sender, place["street_name"], place.get("area"))
                if reply:
                    step("location", started, f"shared pin answered the question: {place['street_name']}")
                    return Outcome(reply, {"reason": "located"}, trace)
            if not rest:
                memory.remember_place(sender, place)
                step("location", started, f"pin kept, waiting for the problem: {place['street_name']}")
                return Outcome(messages.pin_received(place), {"reason": "pin"}, trace)
            text = f"{rest}\nThe resident shared a pin at {place['street_name']}."
        else:
            place = memory.take_place(sender)
            if place and text:
                text = f"{text}\nThe resident shared a pin at {place['street_name']}."
        step("location", started, f"shared pin {place['street_name']}" if place else "no shared pin")

        # 5. Location: a short reply to "which street?", answered offline.
        pending = memory.pending_for(sender)
        if pending and text and not place:
            started = time.perf_counter()
            street = self.location.street_reply(text)
            if street:
                reply = self.fill_pending(pending, sender, street["location"], street["area"])
                step("location", started, f"street reply: {street['label']}")
                if reply:
                    return Outcome(reply, {"reason": "located", "category_id": pending["category_id"],
                                           "location": street["location"]}, trace)
        text, pending = memory.merge_pending(sender, text)

        # 3. Photo: in parallel with triage, never waited for.
        future = self.photo.start(turn.image)
        if future:
            trace.append({"agent": "photo", "ms": 0, "note": "started in parallel"})

        # 2. Triage: the one model call.
        started = time.perf_counter()
        decision = triage.triage(text, turn.image)
        step("triage", started, f"{decision.get('category_id')} {decision.get('reason')}")
        extra = turn.late() if turn.late else None
        if extra:
            text = f"{text}\n{extra}".strip()
            print("[burst] folded a late message into this turn")
            started = time.perf_counter()
            decision = triage.triage(text, turn.image)
            step("triage", started, "again, with a late message")
        decision = apply_place(decision, place)

        net = self.safety.second_net(decision, text)
        if net:
            step("safety", time.perf_counter(), "second net: someone hurt")
            return Outcome(net["reply"], {"reason": "emergency"}, trace)

        started = time.perf_counter()
        decision = self.location.resolve(decision, text)
        step("location", started, decision.get("location") or "none yet")

        # 4. The category specialist.
        specialist = agent_for(decision.get("category_id")) if decision.get("category_id") else None
        if specialist:
            started = time.perf_counter()
            decision = specialist.review(decision, text)
            notes = decision["agent"]["notes"]
            step(f"category:{specialist.id}", started,
                 f"severity {decision.get('severity')} ({decision['agent']['severity_reason']})"
                 + (f"; {'; '.join(notes)}" if notes else ""))

        print(f"[triage] report={decision.get('is_report')} {decision.get('category_id')} "
              f"sev={decision.get('severity')} conf={decision.get('confidence')} why={decision.get('reason')}")

        # 6, 7, 5, 8: duplicate, records, the location question, the reply.
        started = time.perf_counter()
        reply = self.act(decision, sender, text, bool(turn.image), pending, relink_to, turn.photo_ref,
                         link_base=turn.link_base, photo_future=future)
        step("reply", started, decision.get("reason", ""))
        return Outcome(reply, decision, trace)

    # ------------------------------------------------------------------------
    # After triage: the specialists act
    # ------------------------------------------------------------------------
    def act(self, decision, sender, text="", has_photo=False, pending=None, relink_to=None,
            photo=None, link_base=None, photo_future=None):
        """Save what triage accepted, and return the one text the resident gets back."""
        decision = dict(decision)
        decision["has_photo"] = bool(has_photo)
        reason = decision["reason"]
        say, facts = self.reply.say, self.reply.facts
        agent = decision.get("agent") or {}

        # 4. Neighbour problems: the council's own form, never a pin of a home.
        if reason in ("ok", "no_location") and agent.get("handoff"):
            form = agent.get("form_url") or messages.COUNCIL_CONTACT
            return say("handoff", facts(decision, link=form, link_label="Form"),
                       messages.handoff(decision, form))

        # 4b. A real report the model could not map to a confirmed category.
        # Keep the evidence, claim no routing, ask for the one missing field.
        if reason == "needs_capture":
            mode = agent.get("location_mode") or "pin"
            saved = self.records.save(decision, sender, has_photo,
                                      location=decision["location"] or "Not given")
            if not saved.get("ok"):
                print(f"[capture] refused: {saved.get('error')}")
                return say("captured", facts(decision), messages.captured(decision))
            print(f"[captured] {saved['report_id']} from "
                  f"{decision.get('requested_category_id')} "
                  f"({decision.get('requested_reason')})")
            self._attach(saved["report_id"], photo, photo_future)
            link = None
            if not decision["location"]:
                memory.remember_location(sender, text, saved, decision)
                if mode == "pin":
                    link = self.location.map_link(saved["report_id"], base=link_base)
            return say("captured",
                       facts(decision, saved, link=link or saved.get("link")),
                       messages.captured(decision, saved, link))

        # 5. The resident answered our question about where it is: fill that report in.
        if (reason == "ok" and pending and pending.get("report_id")
                and decision["category_id"] == pending.get("category_id")):
            reply = self.fill_pending(pending, sender, decision["location"], decision.get("area"),
                                      decision=decision)
            if reply:
                return reply

        if reason == "ok":
            # 6. The same person, the same open problem: nothing new.
            mine = self.duplicate.same_user(sender, decision["category_id"], decision["location"])
            if mine:
                print(f"[duplicate] {sender[-4:]} already reported this as {mine['id']}")
                return say("already_yours", facts(decision, link=mine["link"]),
                           messages.already_yours(decision, mine["link"]))

            # 7. Records.
            saved = self.records.save(decision, sender, has_photo)
            if not saved.get("ok"):
                print(f"[save] refused: {saved.get('error')}")
                return say("incomplete", facts(decision), messages.need_location(decision))
            print(f"[saved] {saved['report_id']} {decision['category_id']} "
                  f"sev={decision['severity']} duplicate_of={saved['duplicate_of']}")
            self._attach(saved["report_id"], photo, photo_future)

            if saved.get("duplicate_of"):
                return say("duplicate", facts(decision, saved), messages.duplicate(decision, saved))
            if relink_to:
                self.records.link(saved["report_id"], relink_to)
                print(f"[relink] {saved['report_id']} -> {relink_to}")
            return say("saved", facts(decision, saved), messages.logged(decision, saved))

        if reason == "no_location":
            # Act first: keep the report, then ask for the one thing only they know.
            mode = agent.get("location_mode") or "pin"
            saved = self.records.save(decision, sender, has_photo, location="Not given")
            link = None
            if saved.get("ok"):
                memory.remember_location(sender, text, saved, decision)
                self._attach(saved["report_id"], photo, photo_future)
                if mode == "pin":
                    link = self.location.map_link(saved["report_id"], base=link_base)
                print(f"[saved] {saved['report_id']} {decision['category_id']} "
                      "incomplete, waiting for the street")
                if decision["category_id"] == triage.CAPTURE_CATEGORY:
                    return say("captured",
                               facts(decision, saved, link=link or saved.get("link")),
                               messages.captured(decision, saved, link))
            else:
                print(f"[save] refused: {saved.get('error')}")
            extra = {"link": link, "link_label": "Drop a pin"} if link else {}
            return say("incomplete", facts(decision, **extra),
                       messages.need_location(decision, link, mode))

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
                details = facts(decision, link=contact.get("page"), link_label="Details",
                                org=contact.get("org"), contact=contact.get("contact"))
                return say("not_council", details, messages.not_council(decision))

            if is_question(text):
                grounded, _ = rag.answer(text, decision.get("category_id"))
                if grounded:
                    return messages.answered(grounded)

            page = contact.get("page") or messages.COUNCIL_CONTACT
            details = facts(decision, link=page, link_label="The council page", page=page)
            return say("no_answer", details, messages.no_answer(decision))

        return say("unclear", facts(decision), messages.unclear())

    # ------------------------------------------------------------------------
    # The location arriving later: a typed street, a shared pin, the map page
    # ------------------------------------------------------------------------
    def fill_pending(self, pending, sender, location, area=None, decision=None):
        """Put the street on the report we asked about. The reply, or None if it did not land."""
        report_id = pending["report_id"]
        category_id = pending.get("category_id")
        # Someone else's open report of the same thing here: link to it (not ourselves:
        # this report still says "Not given", which never matches).
        original = self._safe(lambda: self.duplicate.same_problem(category_id, location))
        if not self.records.fill_location(report_id, location, area):
            return None
        memory.take_pending_entry(sender)
        if original:
            self.records.link(report_id, original)
        print(f"[located] {report_id} -> {location}")
        filled = dict(decision or {"category_id": category_id,
                                   "category_label": (tools._rulebook()[0].get(category_id) or {}).get("label")})
        filled["location"] = location
        filled["has_photo"] = bool(pending.get("has_photo", filled.get("has_photo")))
        return self.reply.say("saved", self.reply.facts(filled, link=pending["link"]),
                              messages.logged(filled, {"link": pending["link"]}))

    def on_pin_confirmed(self, report_ref, place, source="map"):
        """The map page confirmed a pin: the street goes on the report, the resident is told."""
        report = self.records.report(report_ref)
        street = (place or {}).get("street") or (place or {}).get("area")
        if not report or not street:
            return False
        location_text = self.location.describe(place) or street
        original = self._safe(lambda: self.duplicate.same_problem(report["category_id"], location_text))
        with_db(lambda c: reports_db.set_location_and_area(c, report_ref, location_text, place.get("area")))
        if original and original != report_ref:
            self.records.link(report_ref, original)
        memory.forget_report(report_ref)
        print(f"[located] {report_ref} -> {location_text} (pin, {source})")

        chat = memory.chat_for(report["reporter_ref"])
        if chat and self.notify:
            category = tools._rulebook()[0].get(report["category_id"]) or {}
            told = {"category_id": report["category_id"], "category_label": category.get("label"),
                    "location": street}
            link = f"{tools.SITE_URL}/r/{report['link_token']}"
            text = self.reply.say("located", self.reply.facts(told, link=link),
                                  messages.located(told, link))
            POOL.submit(self.notify, chat, text)
        return True

    def describe_report(self, report_ref):
        """What the map page asks about: 'pothole' in 'Where is the pothole?'."""
        report = self.records.report(report_ref)
        return voice.speak_name(report["category_id"]) if report else None

    # ------------------------------------------------------------------------
    # Photos and status
    # ------------------------------------------------------------------------
    def _attach(self, report_id, photo, photo_future):
        """The photo reference now; the photo agent's features whenever they are ready."""
        if photo and photo[0]:
            self.records.attach_photo(report_id, photo[0], photo[1])
        features = self.photo.ready(photo_future)
        if features:
            self.records.attach_features(report_id, features)
        elif photo_future is not None:
            self.photo.when_done(photo_future, lambda found: self._safe(
                lambda: self.records.attach_features(report_id, found)))

    def late_photo(self, sender, photo_ref, image):
        """A photo on its own: attach it to the one open report, or ask which. None to carry on."""
        if not memory.pending_for(sender):
            fresh = self._fresh_open_reports(sender)
            if len(fresh) > 1:
                print(f"[photo] {len(fresh)} open reports for {sender}, asking which")
                return messages.which_report(fresh)
        attached = self.attach_photo_to_open_report(sender, {"guid": photo_ref[0], "mimeType": photo_ref[1]},
                                                    image)
        if not attached:
            return None
        facts = {"link": attached["link"], "link_label": "Your report"}
        return self.reply.say("photo_added", facts, messages.photo_added(attached["link"]))

    def _fresh_open_reports(self, sender):
        rows = with_db(lambda c: reports_db.open_reports_for(c, tools.reporter_ref(sender))) or []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=LATE_PHOTO_HOURS)
        fresh = []
        for row in rows:
            try:
                created = datetime.fromisoformat(str(row.get("created_at")))
            except (TypeError, ValueError):
                continue
            if created >= cutoff:
                fresh.append(row)
        return fresh

    def attach_photo_to_open_report(self, sender, attachment, image):
        """Attach a late photo to the one open report that needs one."""
        guid = (attachment or {}).get("guid")
        if not guid or not sender:
            return None
        mime = ((attachment or {}).get("mimeType") or (image[1] if image else "") or "").strip()
        pending = memory.PENDING.get(sender) or {}
        if pending.get("report_id") and pending.get("link"):
            report_id, link = pending["report_id"], pending["link"]
        else:
            fresh = self._fresh_open_reports(sender)
            if len(fresh) != 1:   # one report, or we ask which. Never guess.
                return None
            report_id = fresh[0]["id"]
            link = f"{tools.SITE_URL}/r/{fresh[0]['link_token']}"
        if not with_db(lambda c: reports_db.set_photo(c, report_id, guid, mime)):
            return None
        print(f"[photo] attached {guid[:8]} to {report_id}")
        return {"report_id": report_id, "link": link}

    def status_reply(self, sender):
        """Answer from the database, not the model. None when there is nothing to say."""
        report = with_db(lambda c: reports_db.latest_report_for(c, tools.reporter_ref(sender)))
        if not report:
            return None
        report["link"] = f"{tools.SITE_URL}/r/{report['link_token']}"
        report["status_text"] = tools.STATUS_TEXT.get(report["status"], report["status"])
        facts = {"category_id": report["category_id"], "location": report["location"],
                 "status_text": report["status_text"], "link": report["link"]}
        return report, self.reply.say("status", facts, messages.status(report))

    @staticmethod
    def _safe(work):
        """A side lookup that fails must never cost the resident their reply."""
        try:
            return work()
        except Exception as error:  # noqa: BLE001
            print(f"[agents] skipped a side step: {error}")
            return None

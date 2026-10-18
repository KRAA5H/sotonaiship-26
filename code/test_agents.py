"""Tests for the multi-agent workflow: the triage agent orchestrating the others.

No network and no API key: the model, the reverse geocoder and the photo model
are replaced. A temporary database and a temporary pin database are used.

Run: python code/test_agents.py
"""

import json
import os
import sys
import tempfile
import threading
import time
import unittest
import unittest.mock
from concurrent.futures import Future
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import agents  # noqa: E402
import location  # noqa: E402
import pin_service  # noqa: E402
import reports_db  # noqa: E402
import tools  # noqa: E402
import triage  # noqa: E402
import voice  # noqa: E402
import website  # noqa: E402
from agents import Turn, memory  # noqa: E402
from agents.categories import agent_for  # noqa: E402

O = agents.ORCHESTRATOR


def model(**fields):
    """A triage reply, as the model would send it."""
    base = {"is_report": True, "category_id": "pothole", "location": "", "description": "Deep pothole",
            "severity": None, "confidence": 0.9}
    base.update(fields)
    return json.dumps(base)


class FakeGeocoder:
    def __init__(self, street="Windsor Terrace", area="Cultural Quarter", postcode="SO14 7BQ"):
        self.place = {"street_name": street, "area": area, "postcode": postcode}

    def __call__(self):
        return self

    def reverse_geocode(self, latitude, longitude):
        return dict(self.place, latitude=latitude, longitude=longitude)


class AgentCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db_path = Path(self.tmp.name) / "kerbside.db"
        reports_db.init_db(self.db_path)
        self.patch(reports_db, "DB_PATH", self.db_path)
        env = unittest.mock.patch.dict(os.environ, {"SOTONFIX_DB": str(Path(self.tmp.name) / "pin.db")})
        env.start()
        self.addCleanup(env.stop)
        self.patch(tools._location_service, "forward_geocode", None, returns=True)
        self.patch(voice, "generate", None, returns=True)            # templates: deterministic words
        self.patch(location, "LocationService", FakeGeocoder())
        self.patch(O.photo, "start", None, returns=True)
        self.model_calls = []
        self.replies = []
        self.patch(triage.llm, "chat", self._fake_chat)
        self.sent = []
        self.sent_event = threading.Event()
        O.set_notifier(self._notify)
        for store in (memory.PENDING, memory.PLACES, memory.CONTACTS):
            store.clear()

    def patch(self, target, name, value, returns=False):
        patcher = (unittest.mock.patch.object(target, name, return_value=value) if returns
                   else unittest.mock.patch.object(target, name, value))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _fake_chat(self, system, user, image=None, **kwargs):
        self.model_calls.append({"user": user, "image": image, **kwargs})
        return (self.replies.pop(0) if self.replies else model()), "model"

    def _notify(self, chat, text):
        self.sent.append((chat, text))
        self.sent_event.set()

    def turn(self, text, sender="+447700900001", **extra):
        return O.handle(Turn(sender=sender, text=text, chat="chat-" + sender, link_base="https://kerbside.test",
                             **extra))

    def row(self, report_id):
        conn = reports_db.connect(self.db_path)
        try:
            found = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
            return dict(found) if found else None
        finally:
            conn.close()

    def newest(self):
        conn = reports_db.connect(self.db_path)
        try:
            return dict(conn.execute("SELECT * FROM reports ORDER BY CAST(SUBSTR(id, 3) AS INTEGER) DESC "
                                     "LIMIT 1").fetchone())
        finally:
            conn.close()

    def count(self):
        conn = reports_db.connect(self.db_path)
        try:
            return conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
        finally:
            conn.close()


class OrchestratorTest(AgentCase):
    def test_the_triage_agent_runs_the_agents_in_order(self):
        self.replies = [model(location="12 Lawn Road", severity="high")]
        out = self.turn("massive pothole outside 12 lawn road")
        agents_run = [step["agent"] for step in out.trace]
        self.assertEqual(agents_run[:3], ["safety", "location", "triage"])
        self.assertIn("category:pothole", agents_run)
        self.assertEqual(agents_run[-1], "reply")
        self.assertLess(agents_run.index("triage"), agents_run.index("category:pothole"))
        self.assertIn("Logged: pothole, 12 Lawn Road.", out.reply)
        self.assertIn("/r/", out.reply)

    def test_one_model_call_on_the_happy_path(self):
        self.replies = [model(location="Lawn Road")]
        self.turn("pothole on lawn road")
        self.assertEqual(len(self.model_calls), 1)
        call = self.model_calls[0]
        self.assertEqual((call["purpose"], call["temperature"]), ("triage", triage.TRIAGE_TEMPERATURE))
        self.assertLessEqual(call["timeout"], 10)

    def test_the_report_gets_the_official_street_and_area_without_a_lookup(self):
        self.replies = [model(location="lawn rd")]
        self.turn("pothole on lawn rd")
        saved = self.newest()
        self.assertEqual(saved["location"], "Lawn Road")
        self.assertEqual(saved["area"], "Portswood Park")
        tools._location_service.forward_geocode.assert_not_called()

    def test_every_council_report_has_a_severity(self):
        self.replies = [model(location="Lawn Road", severity=None, description="A pothole")]
        self.turn("pothole on lawn road")
        self.assertEqual(self.newest()["severity"], "medium")


class CaptureTest(AgentCase):
    def test_an_info_only_report_is_captured(self):
        self.replies = [model(category_id="flooding_severe_weather", location="",
                              description="tree fallen on the road")]
        out = self.turn("there is a tree fallen on the road")
        row = self.newest()
        self.assertEqual(row["category_id"], "unclear_other")
        self.assertEqual(row["location"], "Not given")
        self.assertIn("can't confirm which council team", out.reply)
        self.assertNotIn("The council has it", out.reply)
        self.assertIn("/p/", out.reply)

    def test_an_unknown_category_is_captured(self):
        self.replies = [model(category_id="tree", location="Weston Lane",
                              description="tree down across the road")]
        out = self.turn("tree down across weston lane")
        row = self.newest()
        self.assertEqual(row["category_id"], "unclear_other")
        self.assertEqual(row["location"], "Weston Lane")
        self.assertIn("/r/", out.reply)

    def test_the_catch_all_with_no_street_says_it_is_not_sent(self):
        self.replies = [model(category_id="unclear_other", location="",
                              description="tree down across the road")]
        out = self.turn("tree down across the road")
        self.assertIn("hasn't gone to the council yet", out.reply)
        self.assertIn("/p/", out.reply)
        self.assertEqual(self.newest()["location"], "Not given")

    def test_a_not_council_report_is_still_never_saved(self):
        self.replies = [model(category_id="not_council_utility", location="Weston Lane",
                              description="gas main being dug up")]
        self.turn("gas main being dug up on weston lane")
        conn = reports_db.connect(self.db_path)
        try:
            saved = conn.execute(
                "SELECT COUNT(*) FROM reports WHERE description = ?",
                ("gas main being dug up",)).fetchone()[0]
            self.assertEqual(saved, 0)
        finally:
            conn.close()


class SafetyTest(AgentCase):
    def test_an_emergency_never_reaches_the_model_or_the_database(self):
        before = self.count()
        out = self.turn("I can smell gas outside number 4")
        self.assertTrue(out.reply.startswith("Call 999 now."))
        self.assertEqual(self.model_calls, [])
        self.assertEqual(self.count(), before)
        self.assertEqual(out.trace[0]["agent"], "safety")

    def test_a_threat_gets_fixed_words(self):
        out = self.turn("I will kill the next person who comes round")
        self.assertIn("If anyone is in danger, call 999.", out.reply)
        self.assertEqual(self.model_calls, [])

    def test_spam_is_silence(self):
        out = self.turn("deals https://a.example https://b.example https://c.example")
        self.assertIsNone(out.reply)

    def test_the_second_net_catches_someone_hurt(self):
        self.replies = [model(location="Lawn Road", severity="high",
                              description="A child fell in the pothole and is bleeding")]
        before = self.count()
        out = self.turn("a kid fell in the pothole on lawn road")
        self.assertTrue(out.reply.startswith("Call 999 now."))
        self.assertEqual(self.count(), before)

    def test_hello_and_thanks_need_no_model(self):
        self.assertIsNone(self.turn("thanks").reply)
        self.assertIn("Hello", self.turn("hello").reply)
        self.assertEqual(self.model_calls, [])


class CategoryAgentTest(AgentCase):
    def test_hazardous_fly_tipping_is_raised(self):
        self.replies = [model(category_id="fly_tipping", location="Lawn Road", severity="low",
                              description="Asbestos sheets dumped")]
        out = self.turn("someone dumped asbestos sheets on lawn road")
        self.assertEqual(out.decision["severity"], "high")
        self.assertIn("hazardous: asbestos", out.decision["agent"]["notes"])
        self.assertEqual(self.newest()["severity"], "high")

    def test_offensive_graffiti_jumps_the_queue(self):
        self.replies = [model(category_id="graffiti_flyposting", location="Lawn Road",
                              description="Racist graffiti on the wall")]
        out = self.turn("racist graffiti on a wall on lawn road")
        self.assertEqual(out.decision["severity"], "high")
        self.assertTrue(any("offensive" in note for note in out.decision["agent"]["notes"]))

    def test_neighbour_noise_goes_to_the_council_form_and_saves_nothing(self):
        before = self.count()
        self.replies = [model(category_id="noise_nuisance", location="", description="Loud music")]
        out = self.turn("my neighbour plays loud music every night")
        self.assertEqual(self.count(), before)
        self.assertIn("Nothing has been logged here.", out.reply)
        self.assertIn(agent_for("noise_nuisance").form_url, out.reply)
        self.assertNotIn("/p/", out.reply)

    def test_a_missed_bin_asks_for_an_address_not_a_pin(self):
        self.replies = [model(category_id="missed_bin", location="", description="Bin not emptied")]
        out = self.turn("my bin wasn't collected")
        self.assertIn("house number and street", out.reply)
        self.assertNotIn("/p/", out.reply)

    def test_every_council_report_category_has_an_agent(self):
        for category_id, category in tools._rulebook()[0].items():
            if category["outcome"] == "council_report":
                self.assertIsNotNone(agent_for(category_id), category_id)
        self.assertTrue(agent_for("pothole").deep)
        self.assertEqual(agent_for("fly_tipping").config["dup_window_days"], 7)


class LocationTest(AgentCase):
    def ask_where(self, sender="+447700900002"):
        self.replies = [model(location="", description="Deep pothole")]
        out = self.turn("there's a pothole near my house", sender=sender)
        return out, self.newest()

    def test_no_street_saves_first_and_offers_the_three_ways(self):
        out, saved = self.ask_where()
        self.assertEqual(saved["location"], "Not given")
        self.assertIn("Reply with the street, share your location, or drop a pin on the map", out.reply)
        self.assertIn("https://kerbside.test/p/", out.reply)
        self.assertEqual(out.reply.count("?"), 1)

    def test_a_typed_street_fills_the_report_with_no_model_call(self):
        _, saved = self.ask_where()
        calls = len(self.model_calls)
        out = self.turn("lawn rd", sender="+447700900002")
        self.assertEqual(len(self.model_calls), calls, "the street reply needs no model")
        filled = self.row(saved["id"])
        self.assertEqual((filled["location"], filled["area"]), ("Lawn Road", "Portswood Park"))
        self.assertIn("Logged: pothole, Lawn Road.", out.reply)
        self.assertIsNone(memory.pending_for("+447700900002"))

    def test_a_house_number_is_kept(self):
        _, saved = self.ask_where()
        self.turn("12 lawn road", sender="+447700900002")
        self.assertEqual(self.row(saved["id"])["location"], "12 Lawn Road")

    def test_a_fragment_is_never_called_outside_southampton(self):
        _, saved = self.ask_where()
        out = self.turn("lawn road", sender="+447700900002")
        self.assertNotIn("not Southampton", out.reply)
        self.assertEqual(self.row(saved["id"])["location"], "Lawn Road")

    def test_outside_southampton_needs_evidence(self):
        self.replies = [model(category_id="outside_southampton", is_report=False, location="Lawn Road")]
        out = self.turn("lawn road pothole")
        self.assertEqual(out.decision["reason"], "unclear")
        self.replies = [model(category_id="outside_southampton", is_report=False, location="Eastleigh")]
        out = self.turn("pothole on the high street in eastleigh")
        self.assertEqual(out.decision["category_id"], "outside_southampton")

    def test_a_shared_pin_answers_the_question(self):
        _, saved = self.ask_where()
        calls = len(self.model_calls)
        out = self.turn("https://maps.apple.com/?ll=50.9069,-1.4058&q=Dropped%20Pin", sender="+447700900002")
        self.assertEqual(len(self.model_calls), calls)
        self.assertEqual(self.row(saved["id"])["location"], "Windsor Terrace")
        self.assertIn("Windsor Terrace", out.reply)

    def test_an_imessage_location_card_works_too(self):
        _, saved = self.ask_where()
        card = "BEGIN:VCARD\nURL;type=pref:http://maps.apple.com/?ll=50.906900\\,-1.405800&q=My%20Location\nEND:VCARD"
        self.turn("", sender="+447700900002", card=card)
        self.assertEqual(self.row(saved["id"])["location"], "Windsor Terrace")

    def test_a_pin_outside_the_city_is_refused_without_a_model_call(self):
        out = self.turn("https://maps.apple.com/?ll=50.9686,-1.3527")   # Eastleigh
        self.assertIn("outside Southampton", out.reply)
        self.assertEqual(self.model_calls, [])

    def test_a_pin_before_the_words_becomes_the_street(self):
        out = self.turn("https://maps.apple.com/?ll=50.9069,-1.4058", sender="+447700900003")
        self.assertIn("Got your pin at Windsor Terrace", out.reply)
        self.replies = [model(category_id="fly_tipping", location="", description="Sofa dumped")]
        out = self.turn("someone dumped a sofa here", sender="+447700900003")
        self.assertIn("shared a pin at Windsor Terrace", self.model_calls[-1]["user"])
        self.assertEqual(self.newest()["location"], "Windsor Terrace")

    def test_a_pin_confirmed_on_the_map_updates_the_report_and_texts_the_resident(self):
        _, saved = self.ask_where()
        place = {"street": "Lawn Road", "landmark": "Portswood Park", "area": "Portswood Park",
                 "postcode": "SO17 2EZ", "coverage": "inside"}
        self.assertTrue(pin_service.HOOKS["on_confirm"](saved["id"], place, "map"))
        self.assertEqual(self.row(saved["id"])["location"], "Lawn Road, near Portswood Park, SO17 2EZ")
        self.assertIsNone(memory.pending_for("+447700900002"))
        self.assertTrue(self.sent_event.wait(5))
        chat, text = self.sent[0]
        self.assertEqual(chat, "chat-+447700900002")
        self.assertIn("Lawn Road", text)
        self.assertIn("/r/", text)

    def test_the_map_page_asks_about_the_right_problem(self):
        _, saved = self.ask_where()
        self.assertEqual(pin_service.HOOKS["describe"](saved["id"]), "pothole")


class DuplicateAgentTest(AgentCase):
    def test_the_same_person_twice_saves_nothing_new(self):
        self.replies = [model(location="Lawn Road"), model(location="Lawn Road")]
        self.turn("pothole on lawn road")
        before = self.count()
        out = self.turn("pothole on lawn road again")
        self.assertEqual(self.count(), before)
        self.assertIn("already reported this one", out.reply)

    def test_someone_else_is_linked_to_the_first(self):
        self.replies = [model(location="Lawn Road"), model(location="Lawn Road")]
        self.turn("pothole on lawn road", sender="+447700900010")
        first = self.newest()
        out = self.turn("pothole on lawn road", sender="+447700900011")
        self.assertEqual(self.newest()["duplicate_of"], first["id"])
        self.assertIn("Already logged", out.reply)

    def test_two_reports_waiting_for_a_street_are_never_linked(self):
        self.replies = [model(location=""), model(location="")]
        self.turn("pothole near me", sender="+447700900012")
        self.turn("pothole near me", sender="+447700900013")
        self.assertIsNone(self.newest()["duplicate_of"])

    def test_each_category_keeps_its_own_window(self):
        old = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat(timespec="seconds")
        conn = reports_db.connect(self.db_path)
        try:
            for rid, category in (("R-9001", "fly_tipping"), ("R-9002", "pothole")):
                conn.execute("INSERT INTO reports (id, created_at, category_id, status, location, description, "
                             "has_photo, link_token) VALUES (?, ?, ?, 'new', 'Lawn Road', 'x', 0, ?)",
                             (rid, old, category, "tok-" + rid))
        finally:
            conn.close()
        self.assertFalse(tools.check_duplicate("fly_tipping", "Lawn Road")["is_duplicate"], "7 day window")
        self.assertEqual(tools.check_duplicate("pothole", "Lawn Road")["duplicate_of"], "R-9002")


class PhotoAgentTest(AgentCase):
    GUID = "iMessage;-;at-0-PHOTO"
    FEATURES = {"what_is_visible": "A deep hole in the tarmac.", "estimated_size": "large",
                "surface": "road", "hazard": "yes", "label": "Deep pothole"}

    def test_the_photo_agent_runs_alongside_triage_and_its_features_are_stored(self):
        started = []

        def start(image):
            started.append(len(self.model_calls))   # before triage's model call
            future = Future()
            future.set_result({"features": self.FEATURES, "problems": [], "mode": "model"})
            return future

        self.patch(O.photo, "start", start)
        self.replies = [model(location="Lawn Road")]
        out = self.turn("pothole on lawn road", image=(b"png", "image/png"),
                        photo_ref=(self.GUID, "image/jpeg"))
        self.assertEqual(started, [0])
        self.assertIn("photo", [step["agent"] for step in out.trace])
        saved = self.newest()
        self.assertEqual(saved["photo_guid"], self.GUID)
        self.assertEqual(json.loads(saved["photo_features"])["hazard"], "yes")

    def test_slow_features_arrive_after_the_reply(self):
        future = Future()
        self.patch(O.photo, "start", lambda image: future)
        self.replies = [model(location="Lawn Road")]
        out = self.turn("pothole on lawn road", image=(b"png", "image/png"),
                        photo_ref=(self.GUID, "image/jpeg"))
        self.assertIsNotNone(out.reply)
        saved = self.newest()
        self.assertIsNone(saved["photo_features"])
        future.set_result({"features": self.FEATURES, "problems": [], "mode": "model"})
        self.assertEqual(json.loads(self.row(saved["id"])["photo_features"])["label"], "Deep pothole")


class StatusAgentTest(AgentCase):
    def saved_report(self):
        self.replies = [model(location="Lawn Road")]
        self.turn("pothole on lawn road", sender="+447700900020")
        return self.newest()

    def test_resolved_texts_the_resident(self):
        report = self.saved_report()
        O.status.on_status_change(report["id"], "resolved")
        self.assertTrue(self.sent_event.wait(5))
        chat, text = self.sent[0]
        self.assertEqual(chat, "chat-+447700900020")
        self.assertIn("resolved", text.lower())

    def test_back_to_new_is_not_worth_a_text(self):
        report = self.saved_report()
        O.status.on_status_change(report["id"], "new")
        time.sleep(0.2)
        self.assertEqual(self.sent, [])

    def test_the_dashboard_button_triggers_the_status_agent(self):
        report = self.saved_report()
        self.assertIn(O.status.on_status_change, website.STATUS_HOOKS)
        app = website.create_app(self.db_path, "pw")
        import base64
        auth = {"Authorization": "Basic " + base64.b64encode(b"x:pw").decode(), "X-Requested-With": "kerbside"}
        hook = unittest.mock.Mock()
        with unittest.mock.patch.object(website, "STATUS_HOOKS", [hook]):
            r = app.test_client().post(f"/council/reports/{report['id']}/status", json={"status": "in_review"},
                                       headers=auth)
        self.assertEqual(r.status_code, 200)
        hook.assert_called_once_with(report["id"], "in_review")


class SpeedTest(AgentCase):
    def test_everything_but_the_model_is_fast(self):
        self.replies = [model(location="12 Lawn Road")]
        started = time.perf_counter()
        self.turn("pothole outside 12 lawn road")
        self.assertLess(time.perf_counter() - started, 0.5, "agent overhead beyond the model call")

    def test_a_street_reply_is_answered_in_milliseconds(self):
        self.replies = [model(location="")]
        self.turn("pothole near my house", sender="+447700900030")
        started = time.perf_counter()
        self.turn("lawn road", sender="+447700900030")
        self.assertLess(time.perf_counter() - started, 0.2)


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""Tests for the temporary simulator. No network, no BlueBubbles.

Run: python code/test_simulator.py
"""

import io
import sys
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import simulator  # noqa: E402

DECISION = {
    "is_report": True, "category_id": "pothole", "category_label": "Pothole",
    "outcome": "council_report", "location": "Alma Road", "description": "Hole",
    "severity": "high", "confidence": 0.9, "reason": "ok",
}
REPLY = "nice one, that's logged - pothole on Alma Road.\nFollow it: https://example.test/r/tok"


class PageTest(unittest.TestCase):
    def setUp(self):
        self.client = simulator.app.test_client()

    def test_the_page_loads(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"street line", response.data)

    def test_health(self):
        self.assertEqual(self.client.get("/health").get_json()["mode"], "simulator")


class TurnTest(unittest.TestCase):
    def setUp(self):
        self.client = simulator.app.test_client()
        self._mode = simulator.MODE
        simulator.MODE = "legacy"
        self.addCleanup(setattr, simulator, "MODE", self._mode)
        # The photo agent would call a model in the background; these tests check the turn.
        patch = unittest.mock.patch.object(simulator.orchestrator.photo, "start", return_value=None)
        patch.start()
        self.addCleanup(patch.stop)

    def test_an_empty_message_is_refused(self):
        response = self.client.post("/api/turn", json={"text": "  "})
        self.assertEqual(response.status_code, 400)

    def test_a_text_turn_returns_body_and_link_separately(self):
        with unittest.mock.patch.object(simulator.triage, "triage", return_value=DECISION), \
             unittest.mock.patch.object(simulator.orchestrator, "act", return_value=REPLY):
            data = self.client.post("/api/turn", json={"text": "pothole on Alma Road"}).get_json()
        self.assertTrue(data["ok"])
        self.assertIn("logged", data["body"])
        self.assertNotIn("http", data["body"])
        self.assertEqual(data["link"], "https://example.test/r/tok")
        self.assertEqual(data["debug"]["category"], "pothole")
        self.assertGreater(data["typing_ms"], 0)

    def test_simulated_typing_can_be_turned_off(self):
        with unittest.mock.patch.object(simulator.triage, "triage", return_value=DECISION), \
             unittest.mock.patch.object(simulator.orchestrator, "act", return_value=REPLY):
            data = self.client.post("/api/turn",
                                    json={"text": "pothole", "simulate": False}).get_json()
        self.assertEqual(data["typing_ms"], 0)

    def test_thanks_gets_silence(self):
        data = self.client.post("/api/turn", json={"text": "thanks"}).get_json()
        self.assertEqual(data["body"], "")
        self.assertEqual(data["link"], "")

    def test_a_photo_reaches_triage_as_bytes(self):
        seen = {}

        def fake_triage(text, image=None):
            seen["image"] = image
            return {**DECISION, "reason": "model_says_not_a_report"}

        with unittest.mock.patch.object(simulator.triage, "triage", side_effect=fake_triage), \
             unittest.mock.patch.object(simulator.orchestrator, "act", return_value="From your photo: a bag."):
            data = self.client.post(
                "/api/turn",
                data={"text": "", "photo": (io.BytesIO(b"png-bytes"), "photo.png")},
                content_type="multipart/form-data",
            ).get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(seen["image"][0], b"png-bytes")
        self.assertTrue(data["debug"]["photo"])


class GraphTurnTest(unittest.TestCase):
    def test_graph_mode_returns_bubbles_and_the_report_link(self):
        class FakeRuntime:
            def __init__(self):
                self.inbound = None

            def turn(self, inbound):
                self.inbound = inbound
                return {
                    "kind": "saved",
                    "bubbles": ["Logged it here.", "Where is it?"],
                    "url": "https://example.test/r/" + "a" * 16,
                    "source_url": None,
                    "state": {
                        "incident_draft": {"category_id": "unclear_other",
                                           "location": {"text": ""}},
                        "executed_outcome": {"action": "log", "saved": True},
                    },
                }

        fake = FakeRuntime()
        with unittest.mock.patch.object(simulator, "MODE", "graph"),              unittest.mock.patch.object(simulator.service, "get_runtime", return_value=fake):
            body, link, debug, started = simulator.run_turn(
                "sim:1", "there is a tree fallen on the road")
        self.assertEqual(body, "Logged it here.\nWhere is it?")
        self.assertEqual(link, "https://example.test/r/" + "a" * 16)
        self.assertEqual(debug["category"], "unclear_other")
        self.assertTrue(debug["is_report"])
        self.assertEqual(fake.inbound["sender"], "sim:1")


class LaterTextsTest(unittest.TestCase):
    def test_a_text_sent_later_reaches_the_chat_once(self):
        client = simulator.app.test_client()
        client.post("/api/turn", json={"text": "thanks"})   # sets the simulator cookie
        sid = client.get_cookie("sim_sid").value
        simulator._to_outbox("sim:" + sid, "Thanks, added: pothole at Lawn Road.\nFollow it: https://x.test/r/t")
        texts = client.get("/api/outbox").get_json()["texts"]
        self.assertEqual(texts, [{"body": "Thanks, added: pothole at Lawn Road.", "link": "https://x.test/r/t"}])
        self.assertEqual(client.get("/api/outbox").get_json()["texts"], [])

    def test_the_map_and_report_pages_are_served_here(self):
        client = simulator.app.test_client()
        self.assertEqual(client.get("/p/some-token-123").status_code, 200)
        self.assertEqual(client.get("/static/pin.js").status_code, 200)
        self.assertEqual(client.get("/r/not-a-real-token").status_code, 404)
        self.assertEqual(client.post("/api/turn", json={"text": " "}).status_code, 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)

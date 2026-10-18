"""Tests for code/photo_features.py and where its output is used. No model calls.

Run:
  python code/test_photo_features.py
"""

import base64
import json
import sys
import tempfile
import unittest
import unittest.mock
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fixtures
import photo_features
import priority
import reports_db
import tools
import website

GOOD = {"what_is_visible": "A deep hole in the tarmac with loose stones around it.",
        "estimated_size": "large", "surface": "road", "hazard": "yes", "label": "Deep pothole in road"}


def fake_chat(reply):
    calls = []

    def chat(system, user, image=None):
        calls.append({"system": system, "user": user, "image": image})
        return (json.dumps(reply) if isinstance(reply, dict) else reply), "model"
    chat.calls = calls
    return chat


class ShapeTest(unittest.TestCase):
    def test_good_reply_passes_unchanged(self):
        features, problems = photo_features.validate(GOOD)
        self.assertEqual(features, GOOD)
        self.assertEqual(problems, [])

    def test_reads_json_in_a_string_or_code_fence(self):
        for raw in (json.dumps(GOOD), f"```json\n{json.dumps(GOOD)}\n```", f"Here you go: {json.dumps(GOOD)}"):
            self.assertEqual(photo_features.validate(raw)[0], GOOD)

    def test_garbage_is_rejected(self):
        for raw in ("I can't see the image", "", None, 42, "[1, 2]", "{not json"):
            features, problems = photo_features.validate(raw)
            self.assertIsNone(features, repr(raw))
            self.assertTrue(problems)

    def test_out_of_range_values_become_unknown(self):
        features, problems = photo_features.validate({**GOOD, "estimated_size": "gigantic", "surface": "lava",
                                                      "hazard": "maybe"})
        self.assertEqual((features["estimated_size"], features["surface"], features["hazard"]),
                         ("unknown", "unknown", "unknown"))
        self.assertEqual(len(problems), 3)

    def test_close_words_are_mapped(self):
        features, _ = photo_features.validate({**GOOD, "surface": "Footpath", "hazard": True,
                                                "estimated_size": "BIG"})
        self.assertEqual((features["surface"], features["hazard"], features["estimated_size"]),
                         ("pavement", "yes", "large"))

    def test_label_is_cut_to_six_words(self):
        features, problems = photo_features.validate({**GOOD, "label": "one two three four five six seven eight"})
        self.assertEqual(features["label"], "one two three four five six")
        self.assertTrue(any("label" in p for p in problems))

    def test_long_description_is_capped(self):
        features, _ = photo_features.validate({**GOOD, "what_is_visible": "word " * 200})
        self.assertLessEqual(len(features["what_is_visible"]), photo_features.MAX_VISIBLE)

    def test_all_unknown_and_no_text_is_nothing(self):
        self.assertIsNone(photo_features.validate({"estimated_size": "unknown"})[0])


class NeverALocationTest(unittest.TestCase):
    """The analysis must never invent or guess a location."""

    PLACES = [
        "A pothole on Portswood Road near the shops.",
        "Rubbish outside SO17 1BJ.",
        "Fly-tipping in Shirley, Southampton.",
        "A broken sign at 50.9097, -1.4044.",
        "A bin left on Burgess Road.",
    ]

    def test_location_fields_are_dropped(self):
        reply = {**GOOD, "location": "Weston Lane", "address": "12 High Street", "postcode": "SO14 7BQ",
                 "lat": 50.9, "lon": -1.4, "where": "by the park"}
        features, problems = photo_features.validate(reply)
        self.assertEqual(set(features), set(photo_features.FIELDS))
        self.assertEqual(sum("location field" in p for p in problems), 6)
        self.assertNotIn("Weston", json.dumps(features))

    def test_text_that_names_a_place_is_rejected(self):
        for text in self.PLACES:
            features, problems = photo_features.validate({**GOOD, "what_is_visible": text, "label": text[:30]})
            dumped = json.dumps(features)
            self.assertIsNone(features["what_is_visible"], text)
            self.assertTrue(any("named a place" in p for p in problems), text)
            for word in ("Portswood", "SO17", "Shirley", "Southampton", "50.9097", "Burgess"):
                self.assertNotIn(word, dumped, text)

    def test_plain_descriptions_are_kept(self):
        for text in ("A sofa and three black bags on a grass verge.", "Broken glass across a cycle path.",
                     "A street sign bent sideways."):
            self.assertEqual(photo_features.validate({**GOOD, "what_is_visible": text})[0]["what_is_visible"], text)

    def test_the_prompt_forbids_places(self):
        self.assertIn("Never say where the photo was taken", photo_features.SYSTEM)
        self.assertNotIn("location", photo_features.FIELDS)

    def test_analyse_end_to_end_with_a_model_that_guesses(self):
        chat = fake_chat({**GOOD, "what_is_visible": "A pothole on Portswood Road.", "location": "Portswood"})
        result = photo_features.analyse((b"png-bytes", "image/png"), chat=chat)
        self.assertNotIn("Portswood", json.dumps(result["features"]))
        self.assertEqual(chat.calls[0]["system"], photo_features.SYSTEM)
        self.assertEqual(chat.calls[0]["image"], (b"png-bytes", "image/png"))

    def test_storing_features_never_touches_the_report_location(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "f.db"
            fixtures.seed(path)
            conn = reports_db.connect(path)
            try:
                before = conn.execute("SELECT location, area FROM reports WHERE id = 'R-0001'").fetchone()
                stored, _ = reports_db.set_photo_features(
                    conn, "R-0001", {**GOOD, "location": "Elsewhere Road", "what_is_visible": "On Elsewhere Road."})
                after = conn.execute("SELECT location, area, photo_features FROM reports WHERE id = 'R-0001'").fetchone()
            finally:
                conn.close()
        self.assertTrue(stored)
        self.assertEqual((before["location"], before["area"]), (after["location"], after["area"]))
        self.assertNotIn("Elsewhere", after["photo_features"])


class SeverityTest(unittest.TestCase):
    NOW = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)

    def report(self, severity="medium", features=None):
        return {"id": "R-1", "category_id": "pothole", "location": "1 Test Road", "severity": severity,
                "status": "new", "created_at": self.NOW.isoformat(),
                "photo_features": json.dumps(features) if features else None}

    def score(self, r):
        return priority.priority(r, [r], {"pothole": "roads_and_parking"}, self.NOW)

    def test_no_features_changes_nothing(self):
        plain = self.score(self.report())
        self.assertEqual(plain["factors"]["severity"]["value"], 2)
        self.assertEqual(plain["factors"]["severity"]["label"], "Medium")

    def test_hazard_and_size_raise_severity_and_say_why(self):
        raised = self.score(self.report(features=GOOD))
        self.assertGreater(raised["factors"]["severity"]["value"], 2)
        self.assertIn("photo: hazard seen", raised["factors"]["severity"]["label"])
        self.assertGreater(raised["score"], self.score(self.report())["score"])

    def test_small_and_harmless_lowers_it(self):
        small = self.score(self.report(features={**GOOD, "hazard": "no", "estimated_size": "small"}))
        self.assertLess(small["factors"]["severity"]["value"], 2)

    def test_stays_within_one_to_three(self):
        high = self.score(self.report("high", GOOD))["factors"]["severity"]["value"]
        low = self.score(self.report("low", {**GOOD, "hazard": "no", "estimated_size": "small"}))
        self.assertEqual(high, 3)
        self.assertEqual(low["factors"]["severity"]["value"], 1)

    def test_invalid_stored_features_are_ignored(self):
        r = self.report()
        r["photo_features"] = "not json at all"
        self.assertEqual(self.score(r)["factors"]["severity"]["value"], 2)


class CouncilPageTest(unittest.TestCase):
    def setUp(self):
        patch = unittest.mock.patch.object(tools._location_service, "forward_geocode", return_value=None)
        patch.start()
        self.addCleanup(patch.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "c.db"
        fixtures.seed(self.path)
        self.client = website.create_app(self.path, "pw").test_client()
        self.auth = {"Authorization": "Basic " + base64.b64encode(b"officer:pw").decode()}

    def reports(self):
        return {r["id"]: r for r in self.client.get("/council/reports.json", headers=self.auth).get_json()["reports"]}

    def test_fixture_data_has_no_model_text(self):
        self.assertTrue(all(r["photo_features"] is None for r in self.reports().values()))

    def test_page_gets_validated_features_only(self):
        conn = reports_db.connect(self.path)
        try:
            reports_db.set_photo_features(conn, "R-0001", GOOD)
            # A row written around the setter, with a place in it, is still cleaned on read.
            conn.execute("UPDATE reports SET photo_features = ? WHERE id = 'R-0002'",
                         (json.dumps({**GOOD, "what_is_visible": "A hole on Hill Lane.", "street": "Hill Lane"}),))
        finally:
            conn.close()
        reports = self.reports()
        self.assertEqual(reports["R-0001"]["photo_features"], GOOD)
        self.assertNotIn("Hill Lane", json.dumps(reports["R-0002"]["photo_features"]))
        self.assertIn("photo: hazard seen", reports["R-0001"]["priority"]["factors"]["severity"]["label"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

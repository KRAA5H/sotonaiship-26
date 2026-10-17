"""Tests for website.py and the database settings it relies on. Standard library plus Flask.

Run:
  python code/test_website.py
"""

import base64
import json
import re
import sys
import tempfile
import threading
import time
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import reports_db
import tools
import website

FAKE = json.loads(reports_db.FAKE_REPORTS_PATH.read_text(encoding="utf-8"))
PASSWORD = "test-password"


def basic(password, user="officer"):
    return {"Authorization": "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()}


AUTH = basic(PASSWORD)
JSON_HEADERS = {**AUTH, "X-Requested-With": "kerbside"}


class SiteCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "site.db"
        self.app = website.create_app(self.path, PASSWORD)
        self.client = self.app.test_client()
        self.conn = reports_db.connect(self.path)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def status_of(self, report_id):
        return self.conn.execute("SELECT status FROM reports WHERE id = ?", (report_id,)).fetchone()[0]

    def council_data(self):
        html = self.client.get("/council", headers=AUTH).get_data(as_text=True)
        blob = re.search(r'<script type="application/json" id="reports">(.*?)</script>', html, re.S)
        return json.loads(blob.group(1))

    def post_status(self, report_id, status, headers=JSON_HEADERS):
        return self.client.post(f"/council/reports/{report_id}/status", json={"status": status},
                                headers=headers)


class DatabaseSettingsTest(SiteCase):
    def test_wal_mode_and_busy_timeout(self):
        self.assertEqual(self.conn.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        self.assertEqual(self.conn.execute("PRAGMA busy_timeout").fetchone()[0],
                         reports_db.BUSY_TIMEOUT_MS)

    def test_writer_waits_for_the_lock_instead_of_failing(self):
        holder = reports_db.connect(self.path)
        holder.execute("BEGIN IMMEDIATE")
        threading.Thread(target=lambda: (time.sleep(0.4), holder.execute("COMMIT")), daemon=True).start()
        started = time.time()
        result = tools.save_report("pothole", "1 Lock Lane", "Hole", conn=self.conn)
        self.assertTrue(result["ok"])
        self.assertGreaterEqual(time.time() - started, 0.3)
        holder.close()

    def test_reads_while_a_write_is_open(self):
        writer = reports_db.connect(self.path)
        writer.execute("BEGIN IMMEDIATE")
        writer.execute("UPDATE reports SET status = 'resolved' WHERE id = 'R-0001'")
        # WAL: the dashboard still reads the last committed state, no waiting.
        response = self.client.get("/council", headers=AUTH)
        self.assertEqual(response.status_code, 200)
        writer.execute("ROLLBACK")
        writer.close()


class CouncilAccessTest(SiteCase):
    def test_needs_the_password(self):
        self.assertEqual(self.client.get("/council").status_code, 401)
        self.assertIn("Basic", self.client.get("/council").headers["WWW-Authenticate"])
        self.assertEqual(self.client.get("/council", headers=basic("wrong")).status_code, 401)
        self.assertEqual(self.client.get("/council", headers=AUTH).status_code, 200)

    def test_switched_off_without_a_password(self):
        app = website.create_app(self.path, council_password="")
        with unittest.mock.patch.dict("os.environ", {"COUNCIL_PASSWORD": ""}):
            response = app.test_client().get("/council")
        self.assertEqual(response.status_code, 503)

    def test_status_change_needs_the_password(self):
        response = self.post_status("R-0001", "resolved", headers={"X-Requested-With": "kerbside"})
        self.assertEqual(response.status_code, 401)
        self.assertNotEqual(self.status_of("R-0001"), "resolved")


class CouncilViewTest(SiteCase):
    def test_lists_every_report(self):
        data = self.council_data()
        self.assertEqual(len(data), len(FAKE))
        self.assertEqual({r["id"] for r in data}, {r["id"] for r in FAKE})

    def test_never_shows_reporter_ref(self):
        html = self.client.get("/council", headers=AUTH).get_data(as_text=True)
        self.assertNotIn("reporter_ref", html)
        for report in FAKE:
            self.assertNotIn(report["reporter_ref"], html)
        hashed = tools.save_report("pothole", "2 Hash Road", "Hole", reporter="+447700900123",
                                   conn=self.conn)
        ref = self.conn.execute("SELECT reporter_ref FROM reports WHERE id = ?",
                                (hashed["report_id"],)).fetchone()[0]
        self.assertNotIn(ref, self.client.get("/council", headers=AUTH).get_data(as_text=True))
        self.assertTrue(all("reporter_ref" not in r for r in self.council_data()))

    def test_shows_category_labels_and_links_to_resident_pages(self):
        html = self.client.get("/council", headers=AUTH).get_data(as_text=True)
        self.assertIn(json.dumps(tools.category_labels()["pothole"]), html)
        self.assertIn("/r/__TOKEN__", html)

    def test_report_text_cannot_break_out_of_the_page(self):
        tools.save_report("pothole", "</script><script>alert(1)</script>", "x", conn=self.conn)
        html = self.client.get("/council", headers=AUTH).get_data(as_text=True)
        self.assertNotIn("<script>alert(1)", html)
        self.assertIn("</script><script>alert(1)</script>",
                      [r["location"] for r in self.council_data()])


class AutoRefreshTest(SiteCase):
    URL = "/council/reports.json"

    def test_needs_the_password(self):
        self.assertEqual(self.client.get(self.URL).status_code, 401)
        self.assertEqual(self.client.get(self.URL, headers=basic("wrong")).status_code, 401)

    def test_returns_the_same_reports_as_the_page(self):
        response = self.client.get(self.URL, headers=AUTH)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.get_json()["reports"], self.council_data())

    def test_never_returns_reporter_ref(self):
        saved = tools.save_report("pothole", "3 Poll Road", "Hole", reporter="+447700900123",
                                  conn=self.conn)
        ref = self.conn.execute("SELECT reporter_ref FROM reports WHERE id = ?",
                                (saved["report_id"],)).fetchone()[0]
        body = self.client.get(self.URL, headers=AUTH).get_data(as_text=True)
        self.assertNotIn("reporter_ref", body)
        self.assertNotIn(ref, body)
        self.assertNotIn("synthetic-", body)

    def test_picks_up_new_reports_and_status_changes(self):
        saved = tools.save_report("dead_animal", "4 Poll Road", "Dead fox", conn=self.conn)
        self.post_status("R-0001", "resolved")
        reports = {r["id"]: r for r in self.client.get(self.URL, headers=AUTH).get_json()["reports"]}
        self.assertIn(saved["report_id"], reports)
        self.assertEqual(reports["R-0001"]["status"], "resolved")

    def test_page_polls_every_15_seconds(self):
        html = self.client.get("/council", headers=AUTH).get_data(as_text=True)
        self.assertIn("REFRESH_MS=15000", html)
        self.assertIn(json.dumps(self.URL), html)


class StatusButtonTest(SiteCase):
    def test_updates_the_database(self):
        for status in ("in_review", "resolved", "new"):
            response = self.post_status("R-0001", status)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json(), {"ok": True, "id": "R-0001", "status": status})
            self.assertEqual(self.status_of("R-0001"), status)

    def test_change_shows_on_the_council_and_resident_pages(self):
        token = FAKE[0]["link_token"]
        self.post_status(FAKE[0]["id"], "resolved")
        self.assertEqual(next(r for r in self.council_data() if r["id"] == FAKE[0]["id"])["status"],
                         "resolved")
        self.assertIn('class="chip s-resolved"', self.client.get(f"/r/{token}").get_data(as_text=True))

    def test_rejects_unknown_status_and_report(self):
        self.assertEqual(self.post_status("R-0001", "deleted").status_code, 400)
        self.assertEqual(self.post_status("R-9999", "resolved").status_code, 404)

    def test_rejects_cross_site_style_requests(self):
        before = self.status_of("R-0001")
        # A plain form post: no JSON, no custom header.
        form = self.client.post("/council/reports/R-0001/status", data={"status": "resolved"},
                                headers=AUTH)
        self.assertEqual(form.status_code, 400)
        # JSON but without the custom header.
        self.assertEqual(self.post_status("R-0001", "resolved", headers=AUTH).status_code, 400)
        self.assertEqual(self.status_of("R-0001"), before)

    def test_get_does_not_change_anything(self):
        self.assertEqual(self.client.get("/council/reports/R-0001/status", headers=AUTH).status_code, 405)


class ResidentViewTest(SiteCase):
    def page(self, token):
        return self.client.get(f"/r/{token}")

    def test_shows_that_one_report(self):
        report = next(r for r in FAKE if r["status"] == "in_review")
        response = self.page(report["link_token"])
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(report["location"], html)
        self.assertIn("In review", html)
        self.assertIn(tools.category_labels()[report["category_id"]], html)

    def test_shows_nothing_from_any_other_report(self):
        report = FAKE[0]
        html = self.page(report["link_token"]).get_data(as_text=True)
        for other in FAKE[1:]:
            self.assertNotIn(other["link_token"], html)
            self.assertNotIn(other["id"], html)
            if other["location"] != report["location"]:
                self.assertNotIn(f">{other['location']}<", html)
        self.assertNotIn("application/json", html)
        self.assertNotIn("<script", html)

    def test_never_shows_its_own_id_or_reporter_ref(self):
        report = FAKE[0]
        html = self.page(report["link_token"]).get_data(as_text=True)
        self.assertNotIn(report["id"], html)
        self.assertNotIn(report["reporter_ref"], html)
        self.assertNotIn("reporter_ref", html)

    def test_repeat_says_someone_else_reported_it(self):
        repeat = next(r for r in FAKE if r["duplicate_of"])
        self.assertIn("Someone has already reported this", self.page(repeat["link_token"]).get_data(as_text=True))

    def test_unknown_token_is_a_404_with_help(self):
        for token in ("doesnotexist1234", "R-0001", "x" * 200):
            response = self.page(token)
            self.assertEqual(response.status_code, 404, token)
            self.assertIn("We can't find that report", response.get_data(as_text=True))

    def test_report_id_is_not_a_way_in(self):
        self.assertEqual(self.page(FAKE[0]["id"]).status_code, 404)

    def test_resident_text_is_escaped(self):
        saved = tools.save_report("pothole", "<b>bold</b> Road", "<img src=x onerror=alert(1)>",
                                  conn=self.conn)
        html = self.page(saved["link_token"]).get_data(as_text=True)
        self.assertNotIn("<b>bold</b>", html)
        self.assertNotIn("<img src=x", html)
        self.assertIn("&lt;b&gt;bold&lt;/b&gt; Road", html)

    def test_report_saved_by_the_agent_opens_from_its_link(self):
        saved = tools.save_report("dead_animal", "Park Road", "Dead fox", conn=self.conn)
        path = saved["link"].split("/", 3)[3]
        response = self.client.get("/" + path)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Dead fox", response.get_data(as_text=True))
        self.assertIn("Received", response.get_data(as_text=True))

    def test_private_headers(self):
        for path, headers in ((f"/r/{FAKE[0]['link_token']}", {}), ("/council", AUTH), ("/r/nope12345", {})):
            response = self.client.get(path, headers=headers)
            self.assertEqual(response.headers["Cache-Control"], "no-store", path)
            self.assertEqual(response.headers["Referrer-Policy"], "no-referrer", path)
            self.assertIn("noindex", response.headers["X-Robots-Tag"], path)

    def test_stylesheet_is_served(self):
        response = self.client.get("/assets/kerbside.css")
        self.assertEqual(response.status_code, 200)
        self.assertIn("--accent", response.get_data(as_text=True))
        response.close()


class WebhookAppTest(unittest.TestCase):
    def test_webhook_server_serves_the_site_on_the_same_port(self):
        import bb
        # Importing blue_bubbles asks BlueBubbles for its own address; skip the network.
        with tempfile.TemporaryDirectory() as tmp,                 unittest.mock.patch.object(bb, "self_address", return_value=""),                 unittest.mock.patch.object(reports_db, "DB_PATH", Path(tmp) / "hook.db"):
            sys.modules.pop("blue_bubbles", None)
            import blue_bubbles
            rules = {r.rule for r in blue_bubbles.app.url_map.iter_rules()}
        self.assertTrue({"/webhook", "/council", "/r/<token>",
                         "/council/reports/<report_id>/status"} <= rules)


if __name__ == "__main__":
    unittest.main(verbosity=2)

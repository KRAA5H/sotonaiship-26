"""Tests that the MCP tickets, the council website and iMessage complaints are
one linked set with no repeats. Runs on throwaway copies of both databases.

Run:  python test_bridge.py
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

TMP = tempfile.mkdtemp()
os.environ["TICKETS_DB_PATH"] = str(Path(TMP) / "tickets.db")
os.environ["DB_PATH"] = str(Path(TMP) / "kerbside.db")  # the website's database
os.environ["KERBSIDE_SYNC"] = "1"

import bridge  # noqa: E402
import db  # noqa: E402
import reports_db  # noqa: E402  (code/, put on the path by bridge)
import tools  # noqa: E402

ALICE, BOB = "+447700900111", "+447700900222"


def count(sql, path=None):
    if path:
        conn = reports_db.connect()
        try:
            return conn.execute(sql).fetchone()[0]
        finally:
            conn.close()
    with db.connect() as conn:
        return conn.execute(sql).fetchone()[0]


def report(report_id):
    conn = reports_db.connect()
    try:
        return dict(conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone())
    finally:
        conn.close()


def web_set_status(report_id, status):
    """What the officer's button on /council does."""
    conn = reports_db.connect()
    try:
        reports_db.set_status(conn, report_id, status)
    finally:
        conn.close()


class Bridge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for f in Path(TMP).glob("*.db*"):
            f.unlink()
        bridge.init()

    def tickets(self):
        return count("SELECT COUNT(*) FROM tickets")

    def reports(self):
        return count("SELECT COUNT(*) FROM reports", path="kerbside")

    def test_1_website_reports_become_tickets_once(self):
        self.assertGreater(self.reports(), 0)
        self.assertEqual(self.tickets(), self.reports(), "one ticket per website report, no MCP seed data")
        before = self.tickets()
        self.assertEqual(bridge.sync()["imported"], 0)
        self.assertEqual(self.tickets(), before, "second sync must not duplicate")

    def test_2_imessage_complaint_reaches_mcp(self):
        saved = tools.save_report("dog_fouling", "12 Testbrook Lane", "Dog mess by the gate",
                                  severity="low", reporter=ALICE)  # the iMessage path
        bridge.sync()
        t = db.tickets_by_report_id()[saved["report_id"]]
        self.assertEqual(t["tracking_token"], saved["link_token"])
        self.assertEqual(t["status"], "TRIAGED")
        self.assertIsNone(t["phone"], "website only has a hash, so no phone")
        found = bridge.nearby("dog_fouling", location_text="12 testbrook lane")
        self.assertEqual([x["ref_code"] for x in found], [t["ref_code"]])

    def test_3_mcp_ticket_shows_on_website_and_resident_page(self):
        t, already = bridge.create(BOB, "pothole", "Deep pothole in the bus lane",
                                   "88 Testford Road", 1, lat=50.93, lng=-1.39)
        self.assertFalse(already)
        r = report(t["report_id"])
        self.assertEqual(r["link_token"], t["tracking_token"])
        self.assertEqual((r["severity"], r["status"], r["location"]), ("high", "new", "88 Testford Road"))
        self.assertEqual(r["reporter_ref"], bridge.reporter_ref(BOB))
        conn = reports_db.connect()
        try:
            council = {x["id"] for x in reports_db.council_reports(conn)}
        finally:
            conn.close()
        self.assertIn(t["report_id"], council, "on /council")
        page = tools.get_report_status(t["tracking_token"])
        self.assertTrue(page["ok"], "on /r/<token>")
        before = self.tickets()
        bridge.sync()
        self.assertEqual(self.tickets(), before, "MCP ticket not re-imported")
        self.assertEqual(self.tickets(), self.reports())

    def test_4_same_resident_same_problem_is_not_repeated(self):
        first, _ = bridge.create(ALICE, "fly_tipping", "Sofa dumped", "5 Repeat Street", 2)
        again, already = bridge.create(ALICE, "fly_tipping", "Sofa still there", "5 repeat street.", 2)
        self.assertTrue(already)
        self.assertEqual(again["ref_code"], first["ref_code"])
        self.assertEqual(count("SELECT COUNT(*) FROM tickets WHERE location_text LIKE '5 Repeat%'"), 1)

    def test_5_texted_then_mcp_same_person_is_one_complaint(self):
        tools.save_report("graffiti_flyposting", "Crossover Lane", "Graffiti on the wall",
                          reporter=BOB)  # Bob texts the bot...
        t, already = bridge.create(BOB, "graffiti_flyposting", "Graffiti on the wall",
                                   "Crossover Lane", 2)  # ...then the agent sees him again
        self.assertTrue(already, "same hash on both channels, so no repeat")

    def test_6_other_resident_is_linked_as_duplicate(self):
        orig, _ = bridge.create(ALICE, "dead_animal", "Dead fox", "Linkage Road", 2)
        dup, already = bridge.create(BOB, "dead_animal", "Dead fox in the road", "linkage road", 2)
        self.assertFalse(already)
        self.assertNotEqual(dup["ref_code"], orig["ref_code"], "Bob gets his own link")
        self.assertEqual(dup["duplicate_of"], orig["ref_code"])
        self.assertEqual(report(dup["report_id"])["duplicate_of"], orig["report_id"], "grouped on /council")
        self.assertEqual([x["ref_code"] for x in bridge.nearby("dead_animal", "Linkage Road")],
                         [orig["ref_code"]], "only originals listed")

    def test_7_coordinates_link_different_street_text(self):
        orig, _ = bridge.create(ALICE, "litter_street_cleaning", "Litter", "Outside the Co-op, Coord Way",
                                3, lat=50.92, lng=-1.40)
        dup, _ = bridge.create(BOB, "litter_street_cleaning", "Rubbish everywhere", "Coord Way shops",
                               3, lat=50.9201, lng=-1.4001)
        self.assertEqual(dup["duplicate_of"], orig["ref_code"])
        self.assertEqual(report(dup["report_id"])["duplicate_of"], orig["report_id"])

    def test_8_officer_clicks_flow_to_mcp_without_ping_pong(self):
        t, _ = bridge.create(ALICE, "missed_bin", "Recycling missed", "9 Status Close", 3)
        db.add_action(t["ref_code"], "Waste collection", 3, "Return to collect")
        web_set_status(t["report_id"], "in_review")
        bridge.sync()
        self.assertEqual(db.get_ticket(t["ref_code"])["status"], "APPROVED")
        web_set_status(t["report_id"], "resolved")
        bridge.sync()
        self.assertEqual(db.get_ticket(t["ref_code"])["status"], "COMPLETED")
        audits = count(f"SELECT COUNT(*) FROM audit_log WHERE ticket_id = {t['id']}")
        bridge.sync()
        bridge.sync()
        self.assertEqual(count(f"SELECT COUNT(*) FROM audit_log WHERE ticket_id = {t['id']}"), audits)
        self.assertEqual(report(t["report_id"])["status"], "resolved")

    def test_9_mcp_side_status_change_reaches_website(self):
        t, _ = bridge.create(BOB, "abandoned_vehicle", "Burnt-out car", "3 Push Street", 1)
        db.set_status(t["ref_code"], "IN_PROGRESS", actor="officer.test")  # e.g. a future dashboard
        bridge.sync()
        self.assertEqual(report(t["report_id"])["status"], "in_review")
        self.assertEqual(db.get_ticket(t["ref_code"])["status"], "IN_PROGRESS", "not pulled back to APPROVED")

    def test_10_resident_sends_street_later(self):
        saved = tools.save_report("pothole", "Not given", "Pothole somewhere", reporter=ALICE)
        conn = reports_db.connect()
        try:
            reports_db.set_location(conn, saved["report_id"], "14 Later Lane")
        finally:
            conn.close()
        bridge.sync()
        self.assertEqual(db.tickets_by_report_id()[saved["report_id"]]["location_text"], "14 Later Lane")


if __name__ == "__main__":
    unittest.main(verbosity=2)

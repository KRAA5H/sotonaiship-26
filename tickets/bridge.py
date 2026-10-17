"""Keeps the MCP tickets (tickets.db) and the website's reports (kerbside.db) in sync.

kerbside.db is what the council sees on /council, what the resident sees on
/r/<token>, and where iMessage complaints are saved (code/tools.py). This
module links each website report to exactly one ticket:

  tickets.report_id      = reports.id            (unique: one report, one ticket)
  tickets.tracking_token = reports.link_token    (same private link for the resident)
  tickets.reporter_ref   = reports.reporter_ref  (same salted hash of the sender)

Sync rules:
  website -> MCP   new reports (e.g. from iMessage) become tickets; an officer's
                   status click (in_review / resolved) moves the ticket on.
  MCP -> website   create_ticket saves the report first via tools.save_report,
                   so the council sees it at once; ticket status changes made
                   elsewhere (db.set_status) are pushed to the report.
  web_status remembers what the website said last time, so we can tell which
  side changed and never ping-pong.

Only reads, inserts and status updates touch kerbside.db, and only through
the teammates' own functions in code/reports_db.py and code/tools.py.

Set KERBSIDE_SYNC=0 to run the MCP standalone (own seed data, no website).
"""
import hashlib
import hmac
import os
import sys
import threading
from pathlib import Path

import db

ROOT = Path(__file__).resolve().parent.parent
ENABLED = os.environ.get("KERBSIDE_SYNC", "1") != "0" and (ROOT / "code" / "reports_db.py").exists()

if ENABLED:
    sys.path.insert(0, str(ROOT / "code"))
    import reports_db  # noqa: E402  (code/reports_db.py, reads DB_PATH from env / code/.env)
    import tools  # noqa: E402  (code/tools.py)

# One lock for every sync and create, so the background sync can never import
# a report half-way through create_ticket making it (which would duplicate it).
LOCK = threading.RLock()

TO_WEB = {
    "RECEIVED": "new", "TRIAGED": "new", "NEEDS_INFO": "new", "PENDING_APPROVAL": "new",
    "APPROVED": "in_review", "ASSIGNED": "in_review", "IN_PROGRESS": "in_review",
    "COMPLETED": "resolved", "REJECTED": "resolved",
}
FROM_WEB = {"new": "TRIAGED", "in_review": "APPROVED", "resolved": "COMPLETED"}
SEVERITY_TO_URGENCY = {"high": 1, "medium": 2, "low": 3}
URGENCY_TO_SEVERITY = {v: k for k, v in SEVERITY_TO_URGENCY.items()}


# --------------------------------------------------------------------------
# Shared helpers (same rules as the website, so one complaint = one match)
# --------------------------------------------------------------------------

def reporter_ref(phone):
    """Same salted hash the iMessage path stores, so one person is one ref
    whether they texted the bot or came through the MCP."""
    if not phone:
        return None
    if ENABLED:
        return tools.reporter_ref(phone)
    salt = (os.getenv("REPORTER_SALT") or "kerbside-dev-salt").encode()
    return "h-" + hmac.new(salt, phone.strip().lower().encode(), hashlib.sha256).hexdigest()[:16]


def same_place(one, other):
    """Same street text, using the website's own duplicate matcher."""
    if not one or not other:
        return False
    if ENABLED:
        return tools._same_place(tools._normalise_location(one), tools._normalise_location(other))
    return " ".join(one.lower().split()) == " ".join(other.lower().split())


def tracking_link(token):
    return f"{tools.SITE_URL}/r/{token}" if ENABLED and token else None


def matches(ticket, location_text=None, lat=None, lng=None, radius_m=200):
    """Distance in metres if the ticket is at this place, else None.
    Coordinates win when both sides have them; otherwise compare street text."""
    if None not in (lat, lng, ticket["lat"], ticket["lng"]):
        d = db.distance_m(lat, lng, ticket["lat"], ticket["lng"])
        return round(d) if d <= radius_m else None
    return 0 if same_place(location_text, ticket["location_text"]) else None


def nearby(category, location_text=None, lat=None, lng=None, radius_m=200, originals_only=True):
    hits = []
    for t in db.open_tickets(category, originals_only=originals_only):
        d = matches(t, location_text, lat, lng, radius_m)
        if d is not None:
            hits.append({**t, "distance_m": d})
    return sorted(hits, key=lambda t: t["distance_m"])


# --------------------------------------------------------------------------
# Start-up and sync
# --------------------------------------------------------------------------

def init():
    db.init_db()
    if ENABLED:
        reports_db.init_db()  # creates kerbside.db (+ teammates' synthetic reports) if missing
        sync()
    else:
        db.seed_if_empty()  # standalone demo data only; never mixed into the website


def sync():
    """One full pass. Safe to call any time; doing it twice changes nothing."""
    if not ENABLED:
        return {"imported": 0, "from_website": 0, "to_website": 0}
    counts = {"imported": 0, "from_website": 0, "to_website": 0}
    with LOCK:
        conn = reports_db.connect()
        try:
            reports = [dict(r) for r in conn.execute("SELECT * FROM reports ORDER BY created_at, id")]
            linked = db.tickets_by_report_id()
            for r in reports:
                t = linked.get(r["id"])
                if t is None:
                    _import(r)
                    counts["imported"] += 1
                    continue
                website_changed = r["status"] != t["web_status"]
                if website_changed and TO_WEB[t["status"]] != r["status"]:
                    db.set_status(t["ref_code"], FROM_WEB[r["status"]], actor="sync:dashboard")
                    counts["from_website"] += 1
                elif not website_changed and TO_WEB[t["status"]] != r["status"]:
                    reports_db.set_status(conn, r["id"], TO_WEB[t["status"]])
                    r["status"] = TO_WEB[t["status"]]
                    counts["to_website"] += 1
                fields = {}
                if r["status"] != t["web_status"]:
                    fields["web_status"] = r["status"]
                if r["location"] != t["location_text"]:  # resident sent the street later
                    fields["location_text"] = r["location"]
                db.update_link_fields(t["ref_code"], **fields)
            _link_duplicates(reports)
        finally:
            conn.close()
    return counts


def _import(report):
    """A website/iMessage report with no ticket yet becomes one."""
    db.create_ticket(
        phone=None,  # the website only ever stores a hash
        category=report["category_id"],
        summary=report["description"],
        location_text=report["location"],
        postcode=None, lat=None, lng=None,
        urgency=SEVERITY_TO_URGENCY.get(report["severity"], 2),
        actor="sync:messages",
        status=FROM_WEB.get(report["status"], "TRIAGED"),
        created_at=report["created_at"],
        report_id=report["id"],
        tracking_token=report["link_token"],
        reporter_ref=report["reporter_ref"],
        web_status=report["status"],
    )


def _link_duplicates(reports):
    """Copy the website's duplicate_of links onto the tickets (as ref_codes)."""
    linked = db.tickets_by_report_id()
    for r in reports:
        t = linked.get(r["id"])
        original = linked.get(r["duplicate_of"]) if r["duplicate_of"] else None
        want = original["ref_code"] if original else None
        if t and want and t["duplicate_of"] != want:
            db.update_link_fields(t["ref_code"], duplicate_of=want)


def start_background_sync(every_s=10):
    """Picks up iMessage complaints and officer clicks while the server runs."""
    def loop():
        while True:
            threading.Event().wait(every_s)
            try:
                sync()
            except Exception as e:  # never kill the server over one bad pass
                print(f"[sync] failed: {e!r}", file=sys.stderr)
    threading.Thread(target=loop, name="kerbside-sync", daemon=True).start()


# --------------------------------------------------------------------------
# Creating a ticket from the MCP
# --------------------------------------------------------------------------

def create(phone, category, summary, location_text, urgency, postcode=None, lat=None, lng=None,
           radius_m=200):
    """Create a ticket with no repeats. Returns (ticket, already_reported).

    1. Same resident, same category, same place, still open: return their
       existing ticket and create nothing.
    2. Otherwise save the report on the website first (tools.save_report:
       its id, private link, reporter hash and street-text duplicate check),
       then the ticket linked to it.
    3. A different resident at the same place still gets their own ticket and
       link, but it is marked duplicate_of the original on both sides.
    """
    ref = reporter_ref(phone)
    with LOCK:
        sync()
        for t in nearby(category, location_text, lat, lng, radius_m, originals_only=False):
            if (ref and t["reporter_ref"] == ref) or (phone and t["phone"] == phone):
                return t, True

        original = next(iter(nearby(category, location_text, lat, lng, radius_m)), None)

        if not ENABLED:
            t = db.create_ticket(phone, category, summary, location_text, postcode, lat, lng,
                                 urgency, reporter_ref=ref)
        else:
            saved = tools.save_report(
                category_id=category, location=location_text, description=summary,
                severity=URGENCY_TO_SEVERITY[urgency], reporter=phone,
            )
            if not saved.get("ok"):
                raise ValueError(saved.get("error", "the website refused the report"))
            t = db.create_ticket(
                phone, category, summary, location_text, postcode, lat, lng, urgency,
                report_id=saved["report_id"], tracking_token=saved["link_token"],
                reporter_ref=ref, web_status="new",
            )
            # The website's own text match missed it, but we know it's the same
            # place (e.g. by coordinates): link it there too.
            if original and not saved.get("duplicate_of") and original["report_id"]:
                conn = reports_db.connect()
                try:
                    reports_db.link_duplicate(conn, saved["report_id"], original["report_id"])
                finally:
                    conn.close()
            _link_duplicates_for(t)

        if original and not t.get("duplicate_of"):
            db.update_link_fields(t["ref_code"], duplicate_of=original["ref_code"])
        return db.get_ticket(t["ref_code"]), False


def _link_duplicates_for(ticket):
    conn = reports_db.connect()
    try:
        row = conn.execute("SELECT duplicate_of FROM reports WHERE id = ?", (ticket["report_id"],)).fetchone()
    finally:
        conn.close()
    if row and row["duplicate_of"]:
        original = db.tickets_by_report_id().get(row["duplicate_of"])
        if original:
            db.update_link_fields(ticket["ref_code"], duplicate_of=original["ref_code"])
            ticket["duplicate_of"] = original["ref_code"]


if __name__ == "__main__":
    init()
    where = reports_db.DB_PATH if ENABLED else "(standalone, no website)"
    print(f"tickets: {db.TICKETS_DB_PATH}\nwebsite: {where}\nsync: {sync()}")

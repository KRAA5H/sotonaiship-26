"""All database access lives here, so we can swap SQLite for Postgres later.

Two data sources:
- Services (read-only): agent/categories.json + agent/confirmed_with_websites.csv.
  A "service" is any category whose outcome is "council_report".
- Live tickets (read/write): SQLite file at TICKETS_DB_PATH. Every complaint
  is saved here as it arrives. Teammates' code reads/writes the same file.
"""
import csv
import json
import math
import os
import random
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
TICKETS_DB_PATH = os.environ.get("TICKETS_DB_PATH", str(HERE / "tickets.db"))
SERVICES_PATH = os.environ.get("SERVICES_PATH", str(HERE.parent / "agent" / "categories.json"))
SERVICES_FACTS_PATH = os.environ.get(
    "SERVICES_FACTS_PATH", str(HERE.parent / "agent" / "confirmed_with_websites.csv")
)

# Other teammates depend on these exact names. Do not rename.
STATUSES = [
    "RECEIVED", "TRIAGED", "NEEDS_INFO", "PENDING_APPROVAL", "APPROVED",
    "ASSIGNED", "IN_PROGRESS", "COMPLETED", "REJECTED",
]
CLOSED_STATUSES = {"COMPLETED", "REJECTED"}


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------
# Services (read-only)
# --------------------------------------------------------------------------

def load_services():
    """Returns {category_id: category dict} for categories the council handles."""
    with open(SERVICES_PATH, encoding="utf-8") as f:
        cats = json.load(f)["categories"]
    return {c["id"]: c for c in cats if c.get("outcome") == "council_report"}


def load_service_facts(category_id):
    """Confirmed facts (with source URL and date) that mention this category."""
    if not os.path.exists(SERVICES_FACTS_PATH):
        return []
    with open(SERVICES_FACTS_PATH, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return [
        {"fact": r["confirmed_fact"], "source_url": r["url"], "date_checked": r["date_checked"]}
        for r in rows
        if category_id in [x.strip() for x in r["category_id"].split(";")]
    ]


# --------------------------------------------------------------------------
# Tickets database
# --------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ref_code TEXT UNIQUE NOT NULL,
    tracking_token TEXT UNIQUE NOT NULL,
    phone TEXT,
    category TEXT NOT NULL,
    summary TEXT,
    location_text TEXT,
    postcode TEXT,
    lat REAL,
    lng REAL,
    urgency INTEGER,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER NOT NULL REFERENCES tickets(id),
    team TEXT,
    priority INTEGER,
    note TEXT,
    status TEXT NOT NULL,
    approved_by TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER REFERENCES tickets(id),
    phone TEXT,
    direction TEXT NOT NULL CHECK (direction IN ('in', 'out')),
    body TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER REFERENCES tickets(id),
    event TEXT NOT NULL,
    actor TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tickets_category ON tickets(category);
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
"""


def connect():
    conn = sqlite3.connect(TICKETS_DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row  # read columns by name
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")  # lets teammates read while we write
    return conn


def init_db():
    with connect() as conn:
        conn.executescript(SCHEMA)


def _new_ref_code(conn):
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I confusion
    while True:
        ref = "SOT-" + "".join(secrets.choice(alphabet) for _ in range(5))
        if not conn.execute("SELECT 1 FROM tickets WHERE ref_code = ?", (ref,)).fetchone():
            return ref


def log_event(conn, ticket_id, event, actor):
    conn.execute(
        "INSERT INTO audit_log (ticket_id, event, actor, created_at) VALUES (?, ?, ?, ?)",
        (ticket_id, event, actor, now()),
    )


def set_status(ref_code, new_status, actor, conn=None):
    """THE way to change a ticket's status. Validates the status name and
    writes an audit_log row. Reuse this from the dashboard etc."""
    if new_status not in STATUSES:
        raise ValueError(f"Unknown status '{new_status}'. Use one of {STATUSES}")
    own_conn = conn is None
    conn = conn or connect()
    try:
        row = conn.execute("SELECT id, status FROM tickets WHERE ref_code = ?", (ref_code,)).fetchone()
        if not row:
            raise ValueError(f"No ticket with ref_code {ref_code}")
        conn.execute(
            "UPDATE tickets SET status = ?, updated_at = ? WHERE id = ?",
            (new_status, now(), row["id"]),
        )
        log_event(conn, row["id"], f"status {row['status']} -> {new_status}", actor)
        if own_conn:
            conn.commit()
    finally:
        if own_conn:
            conn.close()


def create_ticket(phone, category, summary, location_text, postcode, lat, lng, urgency,
                  actor="ai_agent", status="TRIAGED", created_at=None):
    """Saves a new complaint. It starts as RECEIVED, then moves to `status`
    (TRIAGED by default, since the agent has triaged it). Returns the row."""
    ts = created_at or now()
    with connect() as conn:
        ref = _new_ref_code(conn)
        cur = conn.execute(
            """INSERT INTO tickets (ref_code, tracking_token, phone, category, summary,
                   location_text, postcode, lat, lng, urgency, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'RECEIVED', ?, ?)""",
            (ref, secrets.token_urlsafe(32), phone, category, summary, location_text,
             postcode, lat, lng, urgency, ts, ts),
        )
        ticket_id = cur.lastrowid
        log_event(conn, ticket_id, "ticket created", actor)
        conn.execute(
            "INSERT INTO messages (ticket_id, phone, direction, body, created_at) VALUES (?, ?, 'in', ?, ?)",
            (ticket_id, phone, summary, ts),
        )
        if status != "RECEIVED":
            set_status(ref, status, actor, conn=conn)
    return get_ticket(ref)


def get_ticket(ref_code):
    with connect() as conn:
        row = conn.execute("SELECT * FROM tickets WHERE ref_code = ?", (ref_code,)).fetchone()
    return dict(row) if row else None


def get_latest_action(ticket_id):
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM actions WHERE ticket_id = ? ORDER BY id DESC LIMIT 1", (ticket_id,)
        ).fetchone()
    return dict(row) if row else None


def add_action(ref_code, team, priority, note, actor="ai_agent"):
    """Records a PROPOSED action and moves the ticket to PENDING_APPROVAL.
    Nothing is carried out: an officer must approve it on the dashboard."""
    with connect() as conn:
        ticket = conn.execute("SELECT id FROM tickets WHERE ref_code = ?", (ref_code,)).fetchone()
        if not ticket:
            raise ValueError(f"No ticket with ref_code {ref_code}")
        conn.execute(
            """INSERT INTO actions (ticket_id, team, priority, note, status, created_at)
               VALUES (?, ?, ?, ?, 'PROPOSED', ?)""",
            (ticket["id"], team, priority, note, now()),
        )
        log_event(conn, ticket["id"], f"action proposed for {team} (priority {priority})", actor)
        set_status(ref_code, "PENDING_APPROVAL", actor, conn=conn)


def distance_m(lat1, lng1, lat2, lng2):
    """Haversine distance in metres."""
    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def find_nearby_open(lat, lng, category, radius_m=200):
    """Open tickets of the same category within radius_m, nearest first.
    Distance is checked in Python: fine at hackathon scale."""
    placeholders = ",".join("?" * len(CLOSED_STATUSES))
    with connect() as conn:
        rows = conn.execute(
            f"""SELECT * FROM tickets WHERE category = ? AND lat IS NOT NULL AND lng IS NOT NULL
                AND status NOT IN ({placeholders})""",
            (category, *CLOSED_STATUSES),
        ).fetchall()
    hits = []
    for r in rows:
        d = distance_m(lat, lng, r["lat"], r["lng"])
        if d <= radius_m:
            hits.append({**dict(r), "distance_m": round(d)})
    return sorted(hits, key=lambda t: t["distance_m"])


# --------------------------------------------------------------------------
# Seed data (only if the tickets table is empty)
# --------------------------------------------------------------------------

# Approximate coordinates on real Southampton streets.
SEED_STREETS = [
    ("Portswood Road", "SO17", 50.9265, -1.3925),
    ("Burgess Road", "SO16", 50.9345, -1.4010),
    ("Shirley High Street", "SO15", 50.9220, -1.4270),
    ("Bitterne Road West", "SO18", 50.9140, -1.3670),
    ("Above Bar Street", "SO14", 50.9065, -1.4045),
    ("London Road", "SO15", 50.9120, -1.4020),
    ("Bevois Valley Road", "SO14", 50.9165, -1.3955),
    ("Shirley Road", "SO15", 50.9150, -1.4180),
    ("Hill Lane", "SO15", 50.9230, -1.4180),
    ("Portsmouth Road, Woolston", "SO19", 50.8975, -1.3760),
    ("Highfield Lane", "SO17", 50.9300, -1.3950),
    ("Winchester Road", "SO16", 50.9330, -1.4200),
    ("Lodge Road", "SO14", 50.9175, -1.3965),
    ("St Mary Street", "SO14", 50.9070, -1.3950),
    ("Northam Road", "SO14", 50.9100, -1.3880),
]

SEED_SUMMARIES = {
    "fly_tipping": ["Sofa and black bags dumped by the bins", "Mattress left in the alleyway", "Pile of builders' rubble on the verge"],
    "dog_fouling": ["Dog mess all along the pavement near the school", "Regular dog fouling on the grass verge"],
    "dead_animal": ["Dead fox on the pavement", "Dead pigeon by the bus stop"],
    "litter_street_cleaning": ["Litter everywhere outside the shops", "Abandoned shopping trolley on the pavement"],
    "graffiti_flyposting": ["Graffiti sprayed on the bus shelter", "Posters stuck on every lamp post"],
    "glass_spillage_hazard": ["Broken glass across the cycle lane", "Oil spill on the road by the junction"],
    "pothole": ["Deep pothole in the left lane, nearly burst a tyre", "Pothole by the pedestrian crossing", "Road surface breaking up near the bus stop"],
    "abandoned_vehicle": ["Car with flat tyres not moved for months", "Burnt-out car left on the street"],
    "illegal_parking": ["Cars parked on the pavement blocking buggies", "Van parked on double yellows by the school"],
    "noise_nuisance": ["Loud music from a flat every night after midnight", "Dog barking all day at a neighbouring house"],
    "other_nuisance": ["Neighbour burns rubbish every weekend", "Security floodlight shining into bedrooms"],
    "property_concern": ["Front garden piled with rubbish and rats seen", "Empty house with overgrown garden and smell"],
    "missed_bin": ["Recycling bin not collected on Tuesday", "General waste missed again this week"],
    "lost_damaged_bin": ["Recycling bin has gone missing", "Bin lid snapped off during collection"],
    "council_housing_repair": ["Council flat boiler broken, no heating", "Leak through the ceiling of council flat"],
    "unclear_other": ["Something odd happening on the corner, not sure who to tell"],
}

# 40 statuses with a realistic spread.
SEED_STATUSES = (
    ["RECEIVED"] * 3 + ["TRIAGED"] * 6 + ["NEEDS_INFO"] * 3 + ["PENDING_APPROVAL"] * 7
    + ["APPROVED"] * 4 + ["ASSIGNED"] * 4 + ["IN_PROGRESS"] * 5 + ["COMPLETED"] * 6 + ["REJECTED"] * 2
)


def seed_if_empty(n=40):
    with connect() as conn:
        if conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0] > 0:
            return 0
    rng = random.Random(42)  # same seed data every time
    services = load_services()
    categories = [c for c in services if c in SEED_SUMMARIES]
    statuses = SEED_STATUSES[:n]
    rng.shuffle(statuses)
    start = datetime.now(timezone.utc) - timedelta(days=30)

    for i, status in enumerate(statuses):
        # First two tickets: two potholes ~40 m apart on Portswood Road, so
        # duplicate detection has something to find in a demo.
        if i < 2:
            category, street = "pothole", SEED_STREETS[0]
            status = "TRIAGED" if i == 0 else "PENDING_APPROVAL"
        else:
            category, street = rng.choice(categories), rng.choice(SEED_STREETS)
        name, district, lat, lng = street
        lat += rng.uniform(-0.0015, 0.0015) if i >= 2 else i * 0.0004
        lng += rng.uniform(-0.0015, 0.0015) if i >= 2 else 0
        created = (start + timedelta(days=rng.uniform(0, 29), hours=rng.uniform(0, 12))).strftime("%Y-%m-%dT%H:%M:%SZ")
        t = create_ticket(
            phone=f"+447700900{rng.randint(0, 999):03d}",  # Ofcom fictional range
            category=category,
            summary=rng.choice(SEED_SUMMARIES[category]),
            location_text=f"{rng.randint(1, 250)} {name}, Southampton",
            postcode=district,
            lat=round(lat, 6), lng=round(lng, 6),
            urgency=rng.randint(1, 3),
            actor="seed",
            status="RECEIVED",
            created_at=created,
        )
        _seed_walk_to(t, status, services[category]["team"], rng)
    return len(statuses)


def _seed_walk_to(ticket, target, team, rng):
    """Moves a seeded ticket through the normal lifecycle so audit_log looks real."""
    path = {
        "RECEIVED": [],
        "TRIAGED": ["TRIAGED"],
        "NEEDS_INFO": ["TRIAGED", "NEEDS_INFO"],
        "PENDING_APPROVAL": ["TRIAGED", "PROPOSE"],
        "APPROVED": ["TRIAGED", "PROPOSE", "APPROVED"],
        "ASSIGNED": ["TRIAGED", "PROPOSE", "APPROVED", "ASSIGNED"],
        "IN_PROGRESS": ["TRIAGED", "PROPOSE", "APPROVED", "ASSIGNED", "IN_PROGRESS"],
        "COMPLETED": ["TRIAGED", "PROPOSE", "APPROVED", "ASSIGNED", "IN_PROGRESS", "COMPLETED"],
        "REJECTED": ["TRIAGED", "PROPOSE", "REJECTED"],
    }[target]
    ref = ticket["ref_code"]
    for step in path:
        if step == "PROPOSE":
            add_action(ref, team, ticket["urgency"], "Seeded proposal", actor="seed")
        else:
            actor = "officer.demo" if step in ("APPROVED", "ASSIGNED", "REJECTED") else "seed"
            set_status(ref, step, actor)
            if step in ("APPROVED", "REJECTED"):
                with connect() as conn:
                    conn.execute(
                        "UPDATE actions SET status = ?, approved_by = ? WHERE ticket_id = ?",
                        (step, "officer.demo", ticket["id"]),
                    )


if __name__ == "__main__":
    init_db()
    print("seeded", seed_if_empty(), "tickets into", TICKETS_DB_PATH)

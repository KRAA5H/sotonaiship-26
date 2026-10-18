"""Graph storage: threads, idempotency records, the delivery outbox and claims.

SQLite only. Every method opens one short-lived connection through
reports_db.connect, so WAL and the busy timeout match the rest of the app.
The optional profile table is keyed by the salted reporter reference and is
never exposed on a resident page.
"""

import json
from datetime import datetime, timezone

import reports_db

OUTBOX_STATES = ("queued", "sent", "failed", "ambiguous", "undeliverable")
_UNSET = object()

TABLES = """
CREATE TABLE IF NOT EXISTS threads (
  thread_id TEXT PRIMARY KEY,
  active_incident_id TEXT,
  pending_question TEXT,
  last_action TEXT,
  last_claims TEXT,
  last_turn_id TEXT,
  turn_version INTEGER NOT NULL DEFAULT 0,
  incident_draft TEXT,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS turn_operations (
  turn_id TEXT NOT NULL,
  op TEXT NOT NULL,
  result TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (turn_id, op)
);

CREATE TABLE IF NOT EXISTS delivery_outbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  operation_key TEXT UNIQUE NOT NULL,
  thread_id TEXT NOT NULL,
  seq INTEGER NOT NULL,
  body TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'queued',
  attempts INTEGER NOT NULL DEFAULT 0,
  error TEXT,
  created_at TEXT NOT NULL,
  sent_at TEXT
);

CREATE TABLE IF NOT EXISTS claims_sent (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  thread_id TEXT NOT NULL,
  turn_id TEXT NOT NULL,
  bubble TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS profiles (
  thread_id TEXT PRIMARY KEY,
  name TEXT,
  address TEXT,
  phone TEXT,
  style TEXT,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  thread_id TEXT NOT NULL,
  role TEXT NOT NULL,
  text TEXT NOT NULL,
  at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS messages_thread ON messages(thread_id, id);

CREATE TABLE IF NOT EXISTS tasks (
  task_id TEXT PRIMARY KEY,
  thread_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  fields TEXT NOT NULL,
  status TEXT NOT NULL,
  external_ref TEXT,
  link_token TEXT UNIQUE NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
"""


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def migrate(path=None):
    """Create the reports columns and the four graph tables. Idempotent."""
    reports_db.init_db(path)
    conn = reports_db.connect(path)
    try:
        conn.executescript(TABLES)
        try:
            conn.execute("ALTER TABLE profiles ADD COLUMN style TEXT")
        except Exception:  # noqa: BLE001 - the column already exists on a new file
            pass
    finally:
        conn.close()


class _Store:
    def __init__(self, path=None):
        self.path = path

    def _connect(self):
        return reports_db.connect(self.path)


class ThreadStore(_Store):
    def history(self, thread_id, limit=200):
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT role, text, at FROM messages WHERE thread_id = ? "
                "ORDER BY id DESC LIMIT ?", (thread_id, limit)).fetchall()
            return [dict(row) for row in reversed(rows)]
        finally:
            conn.close()

    def append(self, thread_id, role, text, at):
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO messages (thread_id, role, text, at) VALUES (?, ?, ?, ?)",
                (thread_id, role, text, at))
        finally:
            conn.close()

    def load(self, thread_id):
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM threads WHERE thread_id = ?",
                               (thread_id,)).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        data = dict(row)
        for name in ("pending_question", "last_claims", "incident_draft"):
            raw = data.get(name)
            data[name] = json.loads(raw) if raw else None
        return data

    def save(self, thread_id, *, active_incident_id=_UNSET, pending_question=_UNSET,
             last_action=_UNSET, last_claims=_UNSET, last_turn_id=_UNSET,
             incident_draft=_UNSET):
        """Upsert the provided fields and bump turn_version. Omitted fields stay."""
        fields = {}
        for name, value in (("active_incident_id", active_incident_id),
                            ("pending_question", pending_question),
                            ("last_action", last_action),
                            ("last_claims", last_claims),
                            ("last_turn_id", last_turn_id),
                            ("incident_draft", incident_draft)):
            if value is _UNSET:
                continue
            if name in ("pending_question", "last_claims", "incident_draft"):
                fields[name] = json.dumps(value) if value is not None else None
            else:
                fields[name] = value

        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT turn_version FROM threads WHERE thread_id = ?",
                               (thread_id,)).fetchone()
            version = (row["turn_version"] + 1) if row else 1
            columns = ["thread_id", "turn_version", "updated_at", *fields]
            values = [thread_id, version, _now(), *fields.values()]
            placeholders = ",".join("?" for _ in columns)
            updates = "".join(f"{name}=excluded.{name}, " for name in fields)
            sql = (f"INSERT INTO threads ({', '.join(columns)}) VALUES ({placeholders}) "
                   f"ON CONFLICT(thread_id) DO UPDATE SET {updates}"
                   "turn_version=excluded.turn_version, updated_at=excluded.updated_at")
            conn.execute(sql, values)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()
        return self.load(thread_id)


class Outbox(_Store):
    def enqueue(self, thread_id, seq, body, operation_key):
        """Insert once per operation key. Returns the row id, or None if it exists."""
        conn = self._connect()
        try:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO delivery_outbox "
                "(operation_key, thread_id, seq, body, state, created_at) "
                "VALUES (?, ?, ?, ?, 'queued', ?)",
                (operation_key, thread_id, seq, body, _now()),
            )
            return cursor.lastrowid if cursor.rowcount else None
        finally:
            conn.close()

    def pending(self, limit=50):
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM delivery_outbox WHERE state = 'queued' "
                "ORDER BY seq, id LIMIT ?", (limit,)).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def mark(self, row_id, state, error=None):
        if state not in OUTBOX_STATES:
            return False
        conn = self._connect()
        try:
            cursor = conn.execute(
                "UPDATE delivery_outbox SET state = ?, error = ?, sent_at = ?, "
                "attempts = attempts + 1 WHERE id = ?",
                (state, error, _now() if state == "sent" else None, row_id),
            )
            return cursor.rowcount == 1
        finally:
            conn.close()

    def fail_orphans(self):
        """Mark queued rows from a dead process undeliverable. Return the count."""
        conn = self._connect()
        try:
            cursor = conn.execute(
                "UPDATE delivery_outbox SET state = 'undeliverable', "
                "error = COALESCE(error, 'process restarted') WHERE state = 'queued'")
            return cursor.rowcount
        finally:
            conn.close()


class TurnOperations(_Store):
    def get(self, turn_id, op):
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT result FROM turn_operations WHERE turn_id = ? AND op = ?",
                (turn_id, op)).fetchone()
        finally:
            conn.close()
        return json.loads(row["result"]) if row else None

    def record(self, turn_id, op, result):
        """True when this is the first write, False when it was already recorded."""
        conn = self._connect()
        try:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO turn_operations (turn_id, op, result, created_at) "
                "VALUES (?, ?, ?, ?)", (turn_id, op, json.dumps(result), _now()))
            return bool(cursor.rowcount)
        finally:
            conn.close()


class ProfileStore(_Store):
    def history(self, thread_id, limit=200):
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT role, text, at FROM messages WHERE thread_id = ? "
                "ORDER BY id DESC LIMIT ?", (thread_id, limit)).fetchall()
            return [dict(row) for row in reversed(rows)]
        finally:
            conn.close()

    def append(self, thread_id, role, text, at):
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO messages (thread_id, role, text, at) VALUES (?, ?, ?, ?)",
                (thread_id, role, text, at))
        finally:
            conn.close()

    def get(self, thread_id):
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM profiles WHERE thread_id = ?",
                               (thread_id,)).fetchone()
            return dict(row) if row else {}
        finally:
            conn.close()

    def save(self, thread_id, *, name=None, address=None, phone=None, style=None):
        conn = self._connect()
        try:
            now = _now()
            row = conn.execute("SELECT thread_id FROM profiles WHERE thread_id = ?",
                               (thread_id,)).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO profiles (thread_id, name, address, phone, style, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)", (thread_id, name, address, phone, style, now))
            else:
                conn.execute(
                    "UPDATE profiles SET name = COALESCE(?, name), "
                    "address = COALESCE(?, address), phone = COALESCE(?, phone), "
                    "style = COALESCE(?, style), updated_at = ? WHERE thread_id = ?",
                    (name, address, phone, style, now, thread_id))
        finally:
            conn.close()
        return self.get(thread_id)


class TaskStore(_Store):
    REQUIRED = {
        "permit": ("name", "address", "vehicle"),
        "council_tax": ("name", "address"),
        "bins": ("address",),
    }

    def active(self, thread_id):
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM tasks WHERE thread_id = ? AND status IN "
                "('collecting', 'prepared') ORDER BY updated_at DESC LIMIT 1",
                (thread_id,)).fetchone()
            return self._decode(dict(row)) if row else None
        finally:
            conn.close()

    def create(self, thread_id, kind):
        import secrets
        conn = self._connect()
        try:
            last = conn.execute("SELECT MAX(CAST(SUBSTR(task_id, 3) AS INTEGER)) "
                                "FROM tasks WHERE task_id LIKE 'T-%'").fetchone()[0]
            task_id = f"T-{(last or 0) + 1:04d}"
            token = secrets.token_urlsafe(12)
            now = _now()
            conn.execute(
                "INSERT INTO tasks (task_id, thread_id, kind, fields, status, "
                "link_token, created_at, updated_at) VALUES (?, ?, ?, '{}', "
                "'collecting', ?, ?, ?)", (task_id, thread_id, kind, token, now, now))
            return {"task_id": task_id, "thread_id": thread_id, "kind": kind,
                    "fields": {}, "status": "collecting", "external_ref": None,
                    "link_token": token, "created_at": now, "updated_at": now}
        finally:
            conn.close()

    def update_fields(self, task_id, fields):
        task = self.get(task_id)
        if not task:
            return None
        merged = {**(task.get("fields") or {}), **fields}
        conn = self._connect()
        try:
            conn.execute("UPDATE tasks SET fields = ?, updated_at = ? WHERE task_id = ?",
                         (json.dumps(merged), _now(), task_id))
        finally:
            conn.close()
        return self.get(task_id)

    def attach_case(self, task_id, external_ref):
        conn = self._connect()
        try:
            conn.execute("UPDATE tasks SET status = 'prepared', external_ref = ?, "
                         "updated_at = ? WHERE task_id = ?",
                         (external_ref, _now(), task_id))
        finally:
            conn.close()
        return self.get(task_id)

    def get(self, task_id):
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM tasks WHERE task_id = ?",
                               (task_id,)).fetchone()
            return self._decode(dict(row)) if row else None
        finally:
            conn.close()

    def get_by_token(self, token):
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM tasks WHERE link_token = ?",
                               (token,)).fetchone()
            return self._decode(dict(row)) if row else None
        finally:
            conn.close()

    def all(self):
        conn = self._connect()
        try:
            rows = conn.execute("SELECT * FROM tasks ORDER BY created_at DESC").fetchall()
            return [self._decode(dict(row)) for row in rows]
        finally:
            conn.close()

    @staticmethod
    def _decode(row):
        row["fields"] = json.loads(row.get("fields") or "{}")
        return row


class Claims(_Store):
    def record(self, thread_id, turn_id, bubble):
        conn = self._connect()
        try:
            cursor = conn.execute(
                "INSERT INTO claims_sent (thread_id, turn_id, bubble, created_at) "
                "VALUES (?, ?, ?, ?)", (thread_id, turn_id, bubble, _now()))
            return cursor.lastrowid
        finally:
            conn.close()

    def recent(self, thread_id, limit=5):
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT bubble FROM claims_sent WHERE thread_id = ? "
                "ORDER BY id DESC LIMIT ?", (thread_id, limit)).fetchall()
            return [row["bubble"] for row in rows]
        finally:
            conn.close()

# Step 3: storage and migrations

Scope: one step, one commit. `sqlite3` only. No graph, no policy, no writer, no model.

Parent plan: `plans/BUILD-STEPS.md`, Step 3. Architecture: `plans/IMPLEMENTATION_PLAN.md`, section 6.

---

## Context

The contracts exist and the trajectory suite is frozen. The graph still has nowhere to persist a thread, a pending question, a last claim, an idempotency record or an undelivered message.

This step builds that store and settles the D51 migration once. The oracle found the old plan named the `capture_state` and `routing_status` columns in both Step 3 and Step 8, so a builder could not tell who owned them. This plan makes Step 3 the only owner. Step 8 uses the columns and adds nothing.

The Step 2 test doctor is still running. If it finds a real contract defect, it is fixed before this step starts; the Step 2 commit is the baseline.

---

## Files

New:

```text
code/graph/store.py
code/test_graph_store.py
plans/STEP-03-storage.md
```

Changed, only for D51 and D56:

```text
code/reports_db.py       the two additive columns, their defaults, and COLUMNS
dashboard/schema.sql     the same two columns for a fresh database
DECISIONS.md             D56
```

Not touched: `code/graph/{state,schemas,copy_rules}.py`, `code/agents/`, `code/blue_bubbles.py`, `agent/`.

---

## Schema

`store.migrate(path)` calls `reports_db.init_db(path, seed=False)` first, so the D51 columns exist before any graph write, then creates the four tables:

```sql
CREATE TABLE IF NOT EXISTS threads (
  thread_id TEXT PRIMARY KEY,
  active_incident_id TEXT,
  pending_question TEXT,          -- JSON: {field, text, asked_at, turn_id}
  last_action TEXT,
  last_claims TEXT,               -- JSON: [str]
  last_turn_id TEXT,
  turn_version INTEGER NOT NULL DEFAULT 0,
  incident_draft TEXT,            -- JSON: IncidentDraft including version
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS turn_operations (
  turn_id TEXT NOT NULL,
  op TEXT NOT NULL,
  result TEXT NOT NULL,           -- JSON
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
```

And in `reports_db`:

```sql
ALTER TABLE reports ADD COLUMN capture_state TEXT NOT NULL DEFAULT 'captured';
ALTER TABLE reports ADD COLUMN routing_status TEXT NOT NULL DEFAULT 'needs_review';
```

`dashboard/schema.sql` carries the same two columns for a fresh file. `reports_db.COLUMNS` gains them, so `COUNCIL_COLUMNS` and every `SELECT` built from `COLUMNS` stay consistent.

No `CHECK` constraint on `delivery_outbox.state`; the allowed values live in `store.OUTBOX_STATES = ("queued", "sent", "failed", "ambiguous", "undeliverable")`, so a new state does not need a migration.

---

## API

`code/graph/store.py`

```python
OUTBOX_STATES = ("queued", "sent", "failed", "ambiguous", "undeliverable")

def migrate(path=None) -> None
class ThreadStore:
    def __init__(self, path=None)
    def load(self, thread_id) -> dict | None
    def save(self, thread_id, *, active_incident_id=None, pending_question=None,
             last_action=None, last_claims=None, last_turn_id=None,
             incident_draft=None) -> dict
class Outbox:
    def __init__(self, path=None)
    def enqueue(self, thread_id, seq, body, operation_key) -> int | None
    def pending(self, limit=50) -> list[dict]
    def mark(self, row_id, state, error=None) -> bool
    def fail_orphans(self) -> int
class TurnOperations:
    def __init__(self, path=None)
    def get(self, turn_id, op) -> dict | None
    def record(self, turn_id, op, result) -> bool
class Claims:
    def __init__(self, path=None)
    def record(self, thread_id, turn_id, bubble) -> int
    def recent(self, thread_id, limit=5) -> list[str]
```

Rules:

- Every method opens one short-lived connection through `reports_db.connect(path)`, so WAL and the 5s busy timeout match the rest of the app. No global connection.
- `ThreadStore.save` upserts and increments `turn_version` by one. It JSON-encodes `pending_question`, `last_claims` and `incident_draft`, and sets `updated_at` to UTC ISO seconds. `load` decodes them and returns `None` for a missing thread.
- `ThreadStore.load` returns the draft with its own `version` intact, so `apply_patch` can reject a stale write after a restart.
- `Outbox.enqueue` uses `INSERT OR IGNORE` on `operation_key`; a duplicate returns `None`, never a second row. `pending` returns only `queued` rows ordered by `seq, id`.
- `Outbox.mark` accepts only `OUTBOX_STATES`, sets `sent_at` on `sent`, and records `error` on `failed` or `ambiguous`. It returns False for an unknown row or state.
- `Outbox.fail_orphans` marks every `queued` row `undeliverable` and returns how many. The runtime calls it once at startup: a queued row from a dead process has no chat mapping in memory, so it is surfaced on `/council` rather than retried blind.
- `TurnOperations.record` returns True when the row is new and False when it already exists. `execute` uses it to make a replayed node return the recorded result.
- `Claims.record` stores one bubble; `recent` returns the newest first, so a correction can load what was actually said.
- No table stores a chat handle, phone number, name or coordinate. A thread is keyed by the salted `reporter_ref`. The outbox stores `thread_id`, and the channel resolves the chat before sending; if it cannot, the row becomes `undeliverable`.

---

## Tests

`code/test_graph_store.py`, `unittest`, temp database per test, no network.

Migration:

- `migrate` creates the four tables and the two report columns on an empty file;
- calling it twice is a no-op and does not raise;
- an existing `reports` row gets `captured` and `needs_review`;
- `reports_db.COLUMNS` contains `capture_state` and `routing_status`;
- `PRAGMA table_info(reports)` has no duplicates after two runs.

Threads:

- load of a missing thread returns `None`;
- save then load round-trips `pending_question`, `last_claims` and `incident_draft`, including the draft `version`;
- two saves increment `turn_version` to 1 then 2;
- the JSON survives a new `ThreadStore` instance, which is the restart case;
- the threads table has no `chat_guid`, `phone`, `lat` or `lng` column.

Outbox:

- `pending` returns rows in `seq` order, not insertion order;
- the same `operation_key` twice inserts one row and returns `None` the second time;
- `mark` moves `queued` to `sent` and stamps `sent_at`;
- `mark` refuses an unknown state and an unknown row;
- `fail_orphans` marks only queued rows and returns the count;
- a failed or ambiguous row keeps its `error`.

Turn operations and claims:

- `record` then `get` returns the same JSON object;
- a second `record` of the same `(turn_id, op)` returns False and leaves one row;
- `claims.recent` returns newest first and respects the limit.

Isolation:

- `code/graph/store.py` imports only stdlib plus `reports_db`;
- no graph, agent, model or network import in the test.

---

## Verification

```bash
python code/test_graph_store.py
cd code && python -m unittest discover -p "test_*.py"
python code/eval/messages.py
git status --short
```

Acceptance:

- `python code/test_graph_store.py` passes.
- The full suite is 519 plus the new tests, all green, 4 skips.
- `python code/eval/messages.py` stays 31/31.
- The only changed production files are `code/graph/store.py`, `code/reports_db.py` and `dashboard/schema.sql`.
- D56 is recorded in `DECISIONS.md` before the commit.
- One commit: `Add graph storage and outbox`.

---

## What this step does not do

- No graph nodes, no checkpointer, no policy, no writer.
- No change to `tools.save_report`; Step 8 makes it use the new columns.
- No change to `blue_bubbles.py`; Step 11 drains the outbox.
- No backfill of existing reports beyond the column defaults.
- No chat handle stored, so a restart cannot resend an unsent message. That is D56, and the row is surfaced instead.

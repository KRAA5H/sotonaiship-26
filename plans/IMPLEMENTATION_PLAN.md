# Kerbside, LangGraph rebuild: final implementation plan

Status: final plan for approval, 18 Oct 2026, 01:40.
Target: submission locks 13:00 today.
This plan implements the original architecture: one central decision agent, a LangGraph `StateGraph`, selective domain specialists, verified playbooks, capture-first reporting, natural DM bubbles, and truthful outcomes from executed actions.

Nothing here is an incremental patch to `agents/triage_agent.py`. The decision and runtime layer is new. The three capture and truth fixes landed at 01:33 are the semantics the graph inherits, not the solution.

---

## 0. Read this first

The previous attempt fixed three symptoms:

1. `is_report` now governs capture.
2. `save_report` no longer gates on outcome or location.
3. The resident reply is the template, not a model rephrase.

Those are necessary and tested, but they leave the actual architecture untouched: one pass, no persisted claims, no reconsideration, no place for a specialist to disagree, no thread state after a restart. The graph is the change.

What the graph buys, and nothing else buys:

- explicit state that survives a process restart,
- conditional routing, so a decision can be revisited,
- a bounded specialist subgraph that can return `mismatch`,
- one policy gate for every outward claim,
- an outbox that records what was actually sent.

What the graph does not buy: correct facts, correct classification, natural copy, or council integrations. Those remain code and data, and this plan assigns them explicitly.

---

## 1. What we already have, and must use

| Asset | Location | Use in the rebuild |
|---|---|---|
| 22-category rulebook | `agent/categories.json` | Playbook source. 16 `council_report`, 3 `info_only`, 3 `not_council` |
| 54 dated facts | `agent/confirmed_with_websites.csv` | The only permitted fact text. Every claim cites url and `date_checked` |
| Follow-ups, severity hints, form notes | `categories.json` | Specialist requirements. Pothole depth bands, missed-bin checklist, graffiti escalation |
| Boundary and 2,207 streets | `code/geo/` | In/out of city, street normalisation, no postcode-prefix guessing |
| Pin service and map page | `code/pin_service.py`, `code/pin/` | Location without coordinates, 2h token, boundary check before any third party |
| Report store | `code/reports_db.py`, `dashboard/schema.sql` | Single write path, 16 columns today, `new/in_review/resolved` |
| Agent capabilities | `code/agents/{safety,location_agent,duplicate,records,photo,reply,status}.py` | Called as graph tools, not reimplemented |
| Provider ladder | `code/llm.py` | Typed `model/fallback/stub` modes carried into state |
| 68 synthetic reports | `dashboard/fake_reports.*` | Dashboard fixture and duplicate regressions |
| FixMyStreet evaluation | `code/eval/fms/` | Category accuracy baseline 41.7%, duplicate pairs and hard negatives |
| Message evaluation | `code/eval/messages.py` | 31 copy cases |
| 475 unit tests | `code/test_*.py` | Behavioural oracle, offline, ~13s |
| Dashboard and resident pages | `code/website.py`, `code/web/` | `/council`, `/r/<token>`, photo route, status hooks |

There is no tree category. The reported tree conversation is the capture regression, not a product category. Do not invent one.

---

## 2. Invariants the graph enforces

1. Capture is never gated by category or outcome. A plausible physical Southampton problem is retained.
2. Capture is not permission to help. Routing, forms and claims still need verified facts.
3. Never claim council receipt, a crew, a timescale, a reference or a team that was not executed or confirmed.
4. Every factual statement traces to a CSV row with source and date, or to the local record.
5. No coordinates, phone number, name or email in `kerbside.db`. Reporters are salted hashes.
6. Emergency goes to "Call 999 now" from deterministic rules before any model call or tool.
7. Outside Southampton, not-council utilities, unconfirmed trunk roads, and D48 nuisance/property handoffs save nothing.
8. One turn per reporter. Bursts coalesce. No question the resident has already answered.
9. Copy is generated from the executed outcome, then linted. The writer cannot change the action.
10. 1 to 3 bubbles, one purpose each, one URL, no markdown, no em dash, no unconfirmed team.
11. No incident is deleted by a specialist, a validation failure or a correction. Evidence stays.
12. A queued message is not a delivered message.

---

## 3. Target architecture

```text
inbound event (BlueBubbles webhook or simulator)
  -> hydrate        load thread, dedupe message guid, load active incident
  -> precheck       deterministic danger, empty input, burst context
  -> cheap          silence, greeting, status request        -> validate
  -> capture        provisional incident, media refs, location candidates
  -> decide         central decision agent -> TurnPlan
       -> specialist (bounded subgraph) -> reconsider
       -> validate (schema + policy) -> repair once if allowed
  -> execute        approved tools only, idempotent by turn_id
  -> brief          ExecutedOutcome from actual results
  -> compose        writer -> BubblePlan
  -> lint           claim and copy checks; template fallback
  -> enqueue        outbox rows, ordered
  -> END
```

Conditional edges:

- `precheck -> compose` when `short_circuit` is set (emergency, threat, spam, silence, empty).
- `precheck -> cheap` otherwise.
- `cheap -> validate` when handled, else `capture`.
- `decide -> specialist` when `plan.specialist_request` is set and `specialist_call_count < 2`.
- `specialist -> reconsider` always. `reconsider -> specialist` only once, for a `mismatch` with an alternate group. Otherwise `validate`.
- `validate -> repair` when violations are repairable and `repair_count == 0`. `repair -> decide`.
- `validate -> execute` when clean. `validate -> fallback` when hard violations or budget exhausted.
- `execute -> brief -> compose -> lint -> enqueue -> END`.

Checkpointing: `SqliteSaver` in `code/graph.db` (gitignored). `thread_id` is `reporter_ref`. `turn_id` is the inbound `message_guid`. All state JSON-serialisable; attachments are references.

The application truth stays in `kerbside.db`. The checkpoint is execution state. `threads` is the durable application record used for corrections and the dashboard.

---

## 4. State and schemas

`code/graph/state.py`

```python
class IncidentDraft(TypedDict, total=False):
    id: str | None
    capture_state: str          # captured | locally_actionable | submission_ready | submitted
    routing_status: str         # needs_review | verified
    category_candidates: list[dict]   # [{"id": str, "confidence": float}]
    category_id: str | None
    description: str
    location: dict              # text, street, area, postcode, provenance, ambiguous
    attachments: list[dict]     # [{"kind": "photo", "ref": "guid:...", "features": dict | None}]
    severity: str | None
    evidence: list[dict]
    retracted: list[dict]
    version: int

class ThreadState(TypedDict, total=False):
    thread_id: str
    turn_id: str
    recent_messages: list[dict]       # [{role, text, at}], capped at 12
    active_incident_id: str | None
    incident_draft: IncidentDraft
    pending_question: dict | None     # {field, text, asked_at, turn_id}
    last_claims_sent: list[str]
    last_executed_outcome: dict | None
    candidate_services: list[str]
    selected_specialist: str | None
    specialist_results: list[dict]
    plan: dict | None
    repair_count: int
    specialist_call_count: int
    delivery_outbox_ids: list[str]
    degraded: list[str]
    short_circuit: bool
    suppressed: bool
```

`code/graph/schemas.py`

```python
DIALOGUE_ACTS = ("new_report", "detail", "correction", "challenge_previous_claim",
                 "question", "status", "greeting", "other")
ACTIONS = ("log", "ask", "answer", "escalate")
FITS = ("supported", "uncertain", "mismatch")
CAPTURE_STATES = ("captured", "locally_actionable", "submission_ready", "submitted")
ROUTING_STATUSES = ("needs_review", "verified")

validate_turn_plan(raw) -> (plan | None, problems)
validate_specialist_result(raw) -> (result | None, problems)
validate_bubble_plan(raw) -> (plan | None, problems)
apply_patch(draft, patch, version) -> (draft, problems)
```

TurnPlan:

```python
{
  "dialogue_act": str,
  "action": "log" | "ask" | "answer" | "escalate",
  "incident_patch": {"set": {...}, "clear": [...]},   # omitted means unchanged
  "service_candidates": [str],
  "specialist_request": {"group": str, "reason": str} | None,
  "clarification": {"field": str, "reason": str} | None,
  "fact_request": {"question": str, "category_id": str | None} | None,
  "escalation": {"kind": str, "destination": str} | None,
  "retracted_claims": [str],
  "reason_codes": [str]
}
```

SpecialistResult:

```python
{
  "service_id": str,
  "playbook_version": str,
  "fit": str,
  "observations": [str],
  "proposed_patch": {"set": {...}, "clear": [...]},
  "missing_requirements": [str],
  "suggested_question": str | None,
  "recommended_action": str,
  "fact_ids": [str],
  "source_refs": [{"url": str, "date": str}],
  "routing_status": str,
  "reason_codes": [str]
}
```

ExecutedOutcome and BubblePlan:

```python
{
  "action": str, "report_id": str | None, "link_token": str | None,
  "submitted": False, "duplicate_of": str | None,
  "locally_actionable": bool, "missing": [str],
  "facts": [{"fact": str, "url": str, "date": str}],
  "review_queued": bool, "transport": "queued" | "sent" | "failed" | "ambiguous",
  "degraded": [str]
}
{"bubbles": [{"purpose": "repair" | "question" | "action" | "tracking", "text": str}],
 "url": str | None}
```

Patch semantics are enforced in code. A null or missing field never clears location, description or evidence. Clearing requires an explicit `clear` entry with a reason code.

---

## 5. Nodes

`code/graph/nodes.py`, built by `make_nodes(deps)`.

| Node | Reads | Writes | Side effects |
|---|---|---|---|
| hydrate | inbound, threads | thread_id, turn_id, draft, recent_messages, pending_question, suppressed | none |
| precheck | draft, text | short_circuit, plan, degraded | none |
| cheap | text, threads | plan, short_circuit | status read |
| capture | text, attachments, geo/pin | incident_draft, candidate_services | none |
| decide | draft, recent_messages, claims, playbooks | plan, degraded | one model call |
| specialist | plan, draft, playbook, facts | specialist_results, selected_specialist | zero or one model call |
| reconsider | specialist_results | plan, specialist_call_count | none |
| validate | state | violations, repair_count | none |
| repair | violations | plan, repair_count | one model call |
| execute | plan, draft | executed_outcome, draft.id, outbox ids | reports, outbox, location, photo |
| brief | executed_outcome, draft | last_executed_outcome | none |
| compose | outcome, draft, facts | bubble_plan, degraded | one writer call |
| lint | bubble_plan, outcome | bubble_plan, violations | none |
| enqueue | bubble_plan, outcome | delivery_outbox_ids | outbox rows |
| fallback | draft, violations | plan, outcome, review_queued | human review flag |

Dependencies are injected, never imported as globals.

```python
@dataclass(frozen=True)
class Deps:
    llm: object                       # chat(system, user, image=None, **kw) -> (text, mode)
    now: Callable[[], datetime]
    reports: ReportsService
    threads: ThreadStore
    outbox: Outbox
    facts: FactBook
    location: LocationService
    photos: PhotoService
    notifier: Callable[[str, str], tuple[bool, str]]
```

Tests inject fakes. No module-level monkeypatching is required.

---

## 6. Storage and migrations

Additive, run by `reports_db.init_db` on startup.

```sql
ALTER TABLE reports ADD COLUMN capture_state TEXT NOT NULL DEFAULT 'captured';
ALTER TABLE reports ADD COLUMN routing_status TEXT NOT NULL DEFAULT 'needs_review';

CREATE TABLE threads (
  thread_id TEXT PRIMARY KEY,
  active_incident_id TEXT,
  pending_question TEXT,
  last_action TEXT,
  last_claims TEXT,
  last_turn_id TEXT,
  turn_version INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL
);

CREATE TABLE turn_operations (
  turn_id TEXT NOT NULL,
  op TEXT NOT NULL,
  result TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (turn_id, op)
);

CREATE TABLE delivery_outbox (
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

CREATE TABLE claims_sent (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  thread_id TEXT NOT NULL,
  turn_id TEXT NOT NULL,
  bubble TEXT NOT NULL,
  created_at TEXT NOT NULL
);
```

`reports_db.create_report(...)` becomes the only insert. `tools.save_report` delegates to it. `execute` checks `turn_operations` before a write and records the result after, so a replayed node cannot double-write.

No chat handle is persisted. Undeliverable outbox rows after a restart are marked `undeliverable` and shown on `/council`, not retried blind.

`status` stays `new` / `in_review` / `resolved`. Ids stay `R-%04d`. The resident link stays `/r/<link_token>`.

---

## 7. Playbooks and specialists

`code/services/build_playbooks.py` generates one YAML per category from `categories.json` plus the CSV. A test asserts the YAML matches the source, so it cannot drift. `playbook_version` is the categories version plus a hash of the CSV.

| Group | Categories | Handling | What it actually does |
|---|---|---|---|
| cleansing | fly_tipping, dog_fouling, dead_animal, litter_street_cleaning, graffiti_flyposting, glass_spillage_hazard | Subgraph, model only when evidence is ambiguous | Hazardous items, public vs private land, offensive graffiti, glass on a path vs road, size |
| highways | pothole, abandoned_vehicle, illegal_parking | Subgraph | Pothole depth bands from `form_scope_notes`, road vs pavement, vehicle duration and plate, obstruction |
| waste | missed_bin, lost_damaged_bin | Subgraph | Out by 6:30, two working days, report after 4pm, which bin, damaged vs lost |
| housing | council_housing_repair | Subgraph | Tenant or leaseholder, repair type, access, urgency |
| environmental health | noise_nuisance, other_nuisance, property_concern | Deterministic | D48: council form, nothing saved, no address captured |
| info and not-council | info_student_waste_rules, flooding_severe_weather, council_service_other, outside_southampton, not_council_trunk_road, not_council_utility | Deterministic | Grounded answer from facts, or escalate to 999, National Highways, utility, council finder |
| catch-all | unclear_other | Deterministic capture | `routing_status=needs_review`, claim nothing |

A specialist is a compiled subgraph with three nodes: `read_playbook`, `assess`, `result`. It receives the draft, the playbook and the permitted facts explicitly. It cannot write, send, or delete. Its `fit` is one of `supported`, `uncertain`, `mismatch`. A `mismatch` returns to `reconsider` and the incident is untouched.

A specialist that only rephrases a label is not a specialist. It must change its recommendation because of evidence or a tool result, or it does not get a subgraph.

### Playbook health and promotion to a subagent

A group starts on the cheapest handling that can meet its requirements: deterministic where the rules are finite, a subgraph where the reasoning is conditional.

Promotion to a subgraph is allowed only on measured failure, not on preference. A group is promoted when, over at least 20 held-out turns or the trajectory slice, any one of these is true:

- `fit=uncertain` on more than 30% of turns where the playbook carries a requirement;
- `mismatch` or a category change on more than 10%;
- the same missing requirement is asked twice because the playbook cannot tell what is already known;
- an officer edits the category or the requirements on more than 20% of the group's reports;
- any bubble carries a claim the playbook cannot support.

Promotion path:

1. Keep the playbook. It remains the requirements and fact source. A subagent never replaces verified data with prose.
2. Add `code/specialists/<group>.py` with `read_playbook -> assess -> result`, one model call, the group's tools, and a hard timeout.
3. Change the registry entry from `deterministic` to `subgraph`. No other file changes.
4. Run the group's trajectory slice against both, and keep the subgraph only if it wins on completed actionable outcomes without breaking an invariant.

Budget and time:

- At most two promotions before the 12:15 freeze.
- Promotion starts only after Step 3 is green and the trajectory suite runs.
- A subgraph that does not beat the playbook on the slice is deleted, not left in as dead code.
- One promotion at a time, one writer, full suite green between them.

Deterministic groups stay deterministic: environmental health handoff, info/not-council, and catch-all are policy, not reasoning, and do not get a subagent.

The playbook is the source of requirements. `required_local` decides `locally_actionable`. `required_submission` is unknown for every category today, so `submission_ready` is rare and honest, and `submitted` is always false.

---

## 8. Capture and readiness

| State | Meaning | Requires |
|---|---|---|
| captured | evidence retained | description or photo, thread row, report row |
| locally_actionable | an officer could act | description plus resolved location, or an address for address-mode categories |
| submission_ready | destination fields satisfied | a verified `required_submission` set |
| submitted | authoritative acknowledgment | an integration that does not exist in Phase 1 |

Rules:

- `is_report: true` governs capture. The category governs enrichment and outward action.
- `info_only` or an unknown id with `is_report: true` captures as `unclear_other`, `routing_status=needs_review`.
- `outside_southampton`, `not_council_*`, emergency and the three handoff categories save nothing.
- A missing location blocks `locally_actionable`, not capture. It produces exactly one question.
- A correction patches the active incident and records a retraction. It never creates a second row.

Approved capture copy:

```text
i've saved that here. i can't confirm which team owns it, so it hasn't gone to the council yet.
where is it? a street and nearest number, or a pin, is enough.
<private link>
```

---

## 9. Corrections and disagreement

`recent_messages`, `last_claims_sent`, `active_incident_id`, `pending_question` and `retracted` are loaded by `hydrate` and written by `execute`/`brief`.

Challenge detection is deterministic first: "what has that got to do with", "that's not", "i said", "wrong", "no it isn't", "you said". The model is asked only when the regex is ambiguous.

On `challenge_previous_claim`:

1. Load `last_claims_sent`.
2. Populate `retracted_claims` and `draft.retracted`.
3. Keep the incident and its evidence.
4. Compose an acknowledgement that names the correction, then the outstanding question.

Expected regression:

```text
Resident: there is a tree fallen on the road
State:    one incident, unclear_other, needs_review, location missing
Reply:    saved here, not with the council, where is it?

Resident: what has that got to do with flooding
State:    flooding claim retracted, same incident, same pending question
Reply:    you're right, that wasn't flooding. i got that wrong.
          where's the tree? a road and nearest number, or a pin, is enough.
```

Specialist disagreement: one alternate group, then `queue_human_review`. No specialist can refuse capture, delete the incident, send a message or overwrite a resident correction.

---

## 10. Writer and delivery

`code/graph/writer.py` receives `ExecutedOutcome`, the `IncidentDraft` and the permitted facts. It never sees `plan` or the specialist's intentions.

Rules: 1 to 3 bubbles, one purpose each, contractions, lower case, no forced slang, no artificial delay, one URL, no markdown, no em dash, no unconfirmed team, no timescale, no council receipt unless `submitted` with a reference.

`lint` checks the bubbles against `ExecutedOutcome`. A failure falls back to `messages.py` templates, which now say only what happened. The writer cannot set the link; the runtime appends it.

Examples:

```text
captured, location missing:
i've saved that here. i can't confirm which team owns it, so it hasn't gone to the council yet.
where is it? a street and nearest number, or a pin, is enough.
<private link>

saved and locally actionable:
i've saved the pothole report. it hasn't been sent to the council yet.
<private link>

challenge:
you're right, that wasn't flooding. i got that wrong.
where's the tree? a road and nearest number, or a pin, is enough.
```

Delivery: outbox rows in `seq` order, unique `operation_key` per turn and sequence. Words and link are separate rows (D42). A timeout leaves the row `ambiguous`; the brief says so. `claims_sent` records only linted bubbles that were enqueued.

---

## 11. Policy and safety

`code/graph/policy.py` runs deterministic checks. Violation codes:

```text
schema.invalid
action.missing
ask.multiple_targets
ask.known_field
capture.lost
claim.council_receipt
claim.team
claim.number
claim.timescale
copy.lines
copy.urls
copy.markdown
copy.banned
retraction.missing
emergency.tools
not_council.saved
duplicate.unverified
budget.exceeded
```

Repairable: schema, copy, claim, ask. Hard failures: capture lost, not_council saved, emergency tools, budget exceeded. Hard failures go to `fallback`, which composes a safe truthful reply and queues human review when routing is unverified.

Safety: deterministic `precheck` first, never waiting for a model. Urgency (`severity`) and emergency (999 escalation) are separate. A contextual check may add an escalation, never remove one. Emergency never calls a tool.

---

## 12. Budgets and degraded modes

- One decision call, one specialist call, one alternate after mismatch, one repair, one writer call. Hard cap 4 model calls.
- Turn deadline 20s. Model deadline 10s.
- Provider modes `model`, `fallback`, `stub`, `validation_failed` are carried in `degraded` and the brief. A stub is never presented as a successful decision.
- A provider failure preserves the draft and produces a safe, useful response.

---

## 13. Runtime and cutover

`code/graph/runtime.py`

```python
class TurnRuntime:
    def __init__(self, deps: Deps, checkpointer): ...
    def turn(self, inbound: dict) -> dict: ...
    def drain_outbox(self) -> list[dict]: ...
```

- `MODE=graph` on `blue_bubbles.py` and `simulator.py`.
- `MODE=legacy` keeps `TriageAgent` until the trajectory suite is green.
- `python code/graph/runtime.py --turn "there is a tree fallen on the road"` runs one turn without a phone.
- `python code/graph/runtime.py --selftest` runs the trajectory suite against a temp DB.

At cutover: delete `agents/triage_agent.py`, `agents/memory.py`, `triage.normalise`, `conversational_ai.py`, `database.py`. Keep `triage.EMERGENCY_WORDS` by moving it to `graph/precheck.py`.

Dependencies:

```text
langgraph
langgraph-checkpoint-sqlite
flask
requests
python-dotenv
```

Install with `pip install langgraph langgraph-checkpoint-sqlite`, pin the exact versions in `code/requirements.txt`, and record them in `WORKLOG.md` at Step 1. Unit tests use `MemorySaver` and injected fakes, so the suite stays offline. Only the restart test opens `SqliteSaver`. Check the install on the demo Mac before Step 3; if it fails, stop and report, do not improvise a second runtime.

---

## 14. Build order and lane board

Submission locks 13:00. The clock below is deliberate.

| Time | Step | Files | Done when |
|---|---|---|---|
| 01:45-02:30 | 0. Oracle and trajectories | `code/eval/trajectories/*.json`, `test_trajectories.py` | 8 fixtures load; capture, correction, restart, mismatch cases fail against legacy |
| 02:30-04:15 | 1. Foundation | `graph/state.py`, `schemas.py`, `store.py`, `policy.py` | schema, patch and policy unit tests pass offline |
| 04:15-05:45 | 2. Graph shell | `graph/nodes.py` (hydrate, precheck, cheap, capture), `build.py`, `runtime.py` | graph runs one turn, writes a capture row, emergency short-circuits |
| 05:45-07:45 | 3. Decide, validate, execute | `nodes.py` (decide, validate, repair, execute, brief), `services/reports.py` | log, ask, answer, escalate work; one row; no council receipt |
| 07:45-08:15 | Checkpoint | full suite + trajectory slice | end-to-end graph turn on a phone via simulator |
| 08:15-09:45 | 4. Playbooks and one specialist | `services/build_playbooks.py`, `specialists/highways.py`, `registry.py` | supported, uncertain, mismatch; incident preserved |
| 09:45-11:00 | 5. Writer and outbox | `graph/writer.py`, `graph/store.py` outbox methods | natural bubbles, lint, ordered send, ambiguous failure |
| 11:00-11:45 | 6. Channel cutover | `blue_bubbles.py`, `simulator.py` | both channels call the graph; legacy only behind the flag |
| 11:45-12:15 | 7. Corrections and restart | `hydrate`, `reconsider`, `threads` | tree conversation passes; restart keeps pending question |
| 12:15-12:45 | Rehearse and freeze | demo script | live demo path, failure case, no edits after |

Cut line at 08:15: if Step 3 is not green, drop specialist subgraphs and run every category deterministically through the same graph. The runtime, capture, policy, writer and outbox still ship. Do not return to the old pipeline.

Cut line at 11:00: if the writer is not green, use templates and keep `voice.generate` off the send path. The graph still ships.

Promotion rule in flight: if a playbook group fails its trajectory slice before 10:30, promote that one group to a subgraph using section 7. One at a time, two at most, and only if it beats the playbook on the slice.

### Parallel lanes

One writer per tree. Parallel children are read-only unless isolated in a worktree.

| Lane | Type | Owns | Depends on | Returns |
|---|---|---|---|---|
| A foundation | writer | `code/graph/{state,schemas,store,policy}.py` | none | contracts frozen |
| B playbooks | writer | `code/services/*`, `code/specialists/registry.py` | none, reads `agent/` | 22 playbooks, generated and tested |
| C graph shell | writer | `code/graph/{nodes,build,runtime}.py` | A | one turn end to end |
| D decide/execute | writer | `nodes.py` (decide onward), `code/services/reports.py` | A, C | log/ask/answer/escalate |
| E writer/outbox | writer | `code/graph/writer.py`, outbox methods | A | bubbles, lint, ordering |
| F channel | writer | `blue_bubbles.py`, `simulator.py` | C, D, E | both channels on the graph |
| G trajectories | writer | `code/eval/trajectories/`, `test_trajectories.py` | none | 8 fixtures |
| R reviewers | read-only | none | each lane | diff review, policy check |
| S scouts | read-only | none | none | seams, call sites, risks |
| V auditor | read-only | none | any factual claim | CSV row, url, date |

Sequencing rule: A and B may run in parallel. C starts after A. D and E start after C's interfaces are fixed. F after D and E. G starts immediately. Every lane ends with the full suite green.

---

## 15. Tests and acceptance

**Keep**: all 475 tests, except the two gate tests already rewritten, plus the voice send-path tests already replaced.

**Add**:

- capture on `info_only` and unknown ids, with `routing_status=needs_review`;
- challenge retracts and preserves the incident;
- a challenge cannot create a second row;
- null patch cannot clear location or evidence;
- specialist mismatch preserves the draft and reroutes once;
- two incidents switched deliberately;
- duplicate webhook and replay by `turn_id`;
- restart preserves the pending question and marks unsent outbox rows;
- ambiguous send is recorded truthfully;
- prompt injection through text and photo does not change the action;
- budget exhaustion goes to human review;
- every factual bubble has provenance.

**Acceptance**:

1. A wrong category cannot erase a plausible report.
2. A wrong specialist returns `mismatch` and the incident survives.
3. The correction turn retracts the claim and asks the missing field once.
4. A local save cannot produce council receipt.
5. Both channels use one graph.
6. Restart and retry produce one report, not two.
7. 475 tests pass; the 8 trajectories pass; `code/eval/messages.py` passes.
8. The demo path works on the simulator and on iMessage.

---

## 16. Measurement

Primary: completed actionable outcomes per conversation. Report provisional progress separately, so a question is never counted as a completion.

Secondary: category accuracy against the 41.7% keyword baseline, specialist selection accuracy, reroute recovery, false refusal, unnecessary questions, correction recovery, duplicate precision and recall, false capture rate, latency, cost per completed outcome.

`NUMBERS.md` gets one table with a source and date per row, losses included. The current duplicate rule has 17 false positives in 40 non-duplicates; that number goes in the table.

---

## 17. Decisions needed before code

Already recorded: **D50** capture, **D58** `save_report`, **D59** template send path.

Still to sign:

- **D51**: add `capture_state` and `routing_status` columns. `status` unchanged.
- **D52**: correction is a first-class dialogue act with persisted claims and retraction.
- **D53**: the graph replaces the orchestrator. D45 is superseded for the decision layer; the channel and tools remain modules.
- **D54**: the mandatory regression is `flooding_severe_weather` to `unclear_other`, because no tree category or tree fact exists.
- **D55**: the resident page and reply brief stop claiming council review or resolution.
- **D56**: no chat handle persisted; undeliverable outbox rows surface on `/council`.
- **D57**: keep the data and capability layer. The rewrite is the decision and runtime layer only.
- **D60**: playbooks first, subagents on evidence. A group is promoted from deterministic handling to a specialist subgraph only when one of the measured triggers in section 7 fires, the playbook remains the requirements source, and the subgraph beats the playbook on the trajectory slice. At most two promotions before the freeze.

---

## 18. Out of scope

Permit applications, fine challenges, identity documents, fees and acting on a resident's behalf stay in `FUTURE.md`. Phase 1 has no submission integration, so `submitted` is always false and the copy says so. No human-to-human chat. No officer DM.

---

## 19. What this plan will not claim

LangGraph does not fix classification, facts, routing or delivery. It gives explicit state, bounded routing, persistence and human review. Capture, state, policy and truthful copy fix the failure, and the trajectory suite proves each one.

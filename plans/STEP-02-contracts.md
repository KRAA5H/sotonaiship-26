# Step 2: graph contracts (v2)

Status: approved and implemented. The v1 draft was blocked by the Step 2 doctor; this is the corrected contract.
Scope: one step, one commit. Pure Python. No LangGraph, no database, no network, no I/O.

Parent plan: `plans/BUILD-STEPS.md`, Step 2. Architecture: `plans/IMPLEMENTATION_PLAN.md`, sections 4 and 5.

---

## Context

Every later node trusts the same shapes: the plan the model returns, the specialist's result, the incident draft, the executed outcome and the bubbles. If those shapes are loose, a null field can clear a location and a wrong plan can reach the writer.

This step fixes the shapes before any graph exists. It is the contract every later step is tested against.

---

## What changed from v1

The Step 2 doctor found four blocking holes:

1. `ExecutedOutcome` was missing, so Step 9's writer had no typed input.
2. `set` was not validated, so `{"set": {"description": ""}}` could erase the resident's words and `set.attachments` could discard evidence.
3. `version` was optional, so any caller could make an unchecked stale write.
4. Silence had no legal `BubblePlan`, although `thanks` is a real path.

This version fixes all four, plus the non-blocking shape gaps: missing `ThreadState` keys, unvalidated specialist writes, an unrestricted bubble URL, the `"Not given"` contradiction, and the copy-rule import cycle.

---

## Files

New, and only these:

```text
code/graph/__init__.py
code/graph/state.py
code/graph/copy_rules.py
code/graph/schemas.py
code/test_graph_schemas.py
```

Not touched: `code/agents/`, `code/tools.py`, `code/reports_db.py`, `code/blue_bubbles.py`, `agent/`.

---

## Contracts

### state.py

`TypedDict` only, JSON-serialisable, no logic beyond three constructors.

```python
class Location(TypedDict, total=False):
    text: str
    street: str | None
    area: str | None
    postcode: str | None
    provenance: str        # text | pin | gps | postcode | none
    ambiguous: bool

class Attachment(TypedDict, total=False):
    kind: str              # photo
    ref: str               # "guid:..."
    features: dict | None

class CategoryCandidate(TypedDict, total=False):
    id: str
    confidence: float

class IncidentDraft(TypedDict, total=False):
    id: str | None
    capture_state: str
    routing_status: str
    category_candidates: list[CategoryCandidate]
    category_id: str | None
    description: str
    location: Location
    attachments: list[Attachment]
    severity: str | None
    evidence: list[dict]
    retracted: list[dict]
    version: int

class InboundMessage(TypedDict, total=False):
    sender: str
    chat: str
    text: str
    message_guid: str
    image_ref: str | None
    photo_ref: str | None
    card: str

class Message(TypedDict, total=False):
    role: str              # resident | agent
    text: str
    at: str

class PendingQuestion(TypedDict, total=False):
    field: str
    text: str
    asked_at: str
    turn_id: str

class ExecutedOutcome(TypedDict, total=False):
    action: str
    report_id: str | None
    link_token: str | None
    submitted: bool
    duplicate_of: str | None
    locally_actionable: bool
    missing: list[str]
    facts: list[dict]      # {"fact","url","date"}
    review_queued: bool
    transport: str         # queued | sent | failed | ambiguous
    degraded: list[str]
    saved: bool
    refused_reason: str | None

class ThreadState(TypedDict, total=False):
    thread_id: str
    turn_id: str
    inbound: InboundMessage
    recent_messages: list[Message]
    active_incident_id: str | None
    incident_draft: IncidentDraft
    pending_question: PendingQuestion | None
    last_claims_sent: list[str]
    last_executed_outcome: ExecutedOutcome | None
    candidate_services: list[str]
    selected_specialist: str | None
    specialist_results: list[dict]
    plan: dict | None
    violations: list[dict]
    executed_outcome: ExecutedOutcome | None
    bubble_plan: dict | None
    review_queued: bool
    repair_count: int
    specialist_call_count: int
    delivery_outbox_ids: list[str]
    degraded: list[str]
    short_circuit: bool
    suppressed: bool
```

`MAX_RECENT_MESSAGES = 12`.

Constructors: `new_incident_draft(description="", location=None)`, `new_thread_state(thread_id, turn_id)`, `new_executed_outcome(action, saved=False, refused_reason=None)`. Defaults: `capture_state="captured"`, `routing_status="needs_review"`, `version=0`, empty location with `provenance="none"`, `transport="queued"`.

### copy_rules.py

Zero-dependency copy constants, so `schemas.py` does not import `voice.py` (which imports `llm`, which imports `requests`).

```python
MAX_CHARS = 300
MAX_BUBBLES = 3
MARKDOWN = re.compile(r"[*_#`]")
EM_DASH = "\u2014"
EN_DASH = "\u2013"
URLISH = re.compile(
    r"https?://|www\.|google\.|search\?q=|"
    r"\b[a-z0-9-]+\.(?:gov\.uk|co\.uk|org\.uk|ac\.uk|uk|com|org|net|io)\b",
    re.I,
)
REPORT_ID = re.compile(r"\bR-\d{4}\b", re.I)
```

A test asserts these match the patterns in `code/voice.py`, so the two cannot drift.

### Post-review fixes

The Step 2 test doctor probed the contract with malformed plans. Four fixes followed:

1. A non-dict `set` or `add` could crash `_validate_patch_shape` after it had already recorded the problem. Both loops are now guarded by `isinstance`, so a malformed model plan earns `patch.unknown_key:set`, not an `AttributeError`.
2. Plan-level patches did not validate nested keys. `set.location` now rejects `lat`, and `add.attachments`, `add.evidence` and `add.retracted` check their item keys and enums.
3. A whitespace `street` could overwrite a real one. Empty and whitespace-only location strings are now rejected.
4. `new_executed_outcome("log")` had no representable state when nothing was saved and nothing was refused. A `log` now needs `refused_reason`; `ask`, `answer` and `escalate` may write nothing. The description is no longer truncated to 400 characters, because the resident's words are the audit record.

An explicit `{}` patch is rejected as `patch.unknown_key`, while an omitted patch is valid and `{"set": {}}` is a `patch.no_change`.

### schemas.py

Enums:

```python
DIALOGUE_ACTS = ("new_report", "detail", "correction", "challenge_previous_claim",
                 "question", "status", "greeting", "other")
ACTIONS = ("log", "ask", "answer", "escalate")
FITS = ("supported", "uncertain", "mismatch")
CAPTURE_STATES = ("captured", "locally_actionable", "submission_ready", "submitted")
ROUTING_STATUSES = ("needs_review", "verified")
PROVENANCE = ("text", "pin", "gps", "postcode", "none")
BUBBLE_PURPOSES = ("repair", "question", "action", "tracking")
TRANSPORT_STATES = ("queued", "sent", "failed", "ambiguous")
CATEGORY_OUTCOMES = ("council_report", "info_only", "not_council")
SEVERITIES = ("high", "medium", "low")
MESSAGE_ROLES = ("resident", "agent")
ATTACHMENT_KINDS = ("photo",)
SPECIALIST_GROUPS = ("cleansing", "highways", "waste", "housing")
ESCALATION_KINDS = ("emergency_999", "national_highways", "utility",
                    "council_complaints", "council_out_of_hours",
                    "adult_social_care", "council_finder", "council_form")
CLEAR_REASONS = ("resident_correction", "new_incident", "wrong_place", "no_longer_relevant")
LOCATION_UNKNOWN = "Not given"
```

Validators return `(value | None, list[str])`. Problems are strings of the form `code` or `code:field`.

```python
validate_turn_plan(raw, allow_emergency=False)
validate_specialist_result(raw, today=None)
validate_bubble_plan(raw, allow_suppressed=False)
validate_incident_draft(raw)
validate_executed_outcome(raw)
validate_thread_state(raw, today=None)
apply_patch(draft, patch, version, reason_codes=None, today=None)
set_policy_fields(draft, capture_state=None, routing_status=None, reason=None)
```

Rules:

- Unknown keys at any level are rejected. A typo must fail, not disappear.
- `validate_turn_plan` requires `dialogue_act` and `action` from the enums, and enforces compatibility: report acts can log or ask, question can answer or escalate, status can answer, greeting can ask or answer.
- `action="ask"` requires exactly one `clarification` with a non-empty `field` and `reason`; any other action requires `clarification` to be null.
- `action="answer"` requires a non-null `fact_request` with a non-empty `question`.
- `action="escalate"` requires `kind` from `ESCALATION_KINDS` and a non-empty `destination`. A model plan may not use `emergency_999`; only precheck may. Membership of the destination in the fact-sheet allowlist is checked by policy in Step 4, because `schemas.py` may not read `agent/`.
- `specialist_request.group` must be one of `SPECIALIST_GROUPS`. `service_candidates` are strings; category membership is policy's job in Steps 4 and 5.
- `validate_specialist_result`: `fit`, `recommended_action` and `routing_status` from their enums; `fit="mismatch"` needs non-empty observations; `fit="supported"` needs non-empty `source_refs` and `fact_ids`; `fact_ids` match `^F\d+$`; source URLs are http or https and dates are `YYYY-MM-DD` not in the future; `proposed_patch` must pass the same shape check as a plan patch. It is applied only through `apply_patch`.
- `validate_bubble_plan`: 1 to 3 bubbles, each one line, non-empty, at most 300 characters, no markdown, no em dash, no en dash, no URL-ish text, no report id. `url` is null or `^https?://[^/]+/r/[A-Za-z0-9_-]{16,}$`. The writer emits null; the runtime fills it. A suppressed plan is `{"bubbles": [], "url": null, "suppressed": true}` and is valid only with `allow_suppressed=True`.
- `validate_executed_outcome`: action from `ACTIONS`, report id `^R-\d{4}$`, token 8 to 64 characters, transport from `TRANSPORT_STATES`, facts with url and date, and `saved` plus `refused_reason`. A saved outcome needs a report id. A `log` that saved nothing needs a refusal reason; an `ask`, `answer` or `escalate` may write nothing.
- `validate_incident_draft`: enum fields, no `lat` or `lng` anywhere, attachments with `kind` from the enum, evidence keys limited to `kind`, `ref`, `text`, `at`, `source`, so a phone number or coordinate cannot ride along.
- `validate_thread_state`: every nested field validated, `recent_messages` capped at 12, and `plan`/`specialist_results`/`executed_outcome`/`bubble_plan` validated when present.

### Patch semantics

The failure this prevents: a model returns `{"location": null}` or `{"set": {"description": ""}}` and wipes what the resident already gave.

- The patch must be a dict whose keys are a subset of `{"set", "clear", "add"}`. A flat patch, `None`, `{}`, or an unknown key is rejected as `patch.unknown_key`. The draft is returned unchanged.
- `set` keys must be a subset of `PATCHABLE = {"category_id", "category_candidates", "description", "location", "severity"}`. Unknown keys are rejected.
- `add` keys must be a subset of `{"attachments", "evidence", "retracted"}`. These fields are append-only and the only way to write them. Duplicate attachment `ref` or retraction `claim` is ignored, not duplicated.
- `clear` may contain only `category_id`, `category_candidates`, `severity`, or `location`. `location` may be cleared only when its `text` is empty or `LOCATION_UNKNOWN` compared case-insensitively. `description`, `evidence`, `attachments`, `retracted`, `id`, `capture_state`, `routing_status` and `version` can never be cleared.
- Every `clear` requires at least one reason code from `CLEAR_REASONS`; otherwise `patch.clear_without_reason`.
- In `set.location`, `None` means omitted. An empty or whitespace-only `text`, `street`, `area` or `postcode` is rejected as `patch.empty_value`, never written as a blank. An unknown location key such as `lat` is rejected. A `set` that would blank a non-empty description is rejected the same way.
- Policy-owned fields are rejected in a patch: `id`, `capture_state`, `routing_status`, `version`.
- `version` is a required positional argument. If it does not equal `draft["version"]`, return the original draft and `patch.stale_version`.
- A patch that changes nothing returns the original draft and `patch.no_change`, without bumping the version.
- On success, return a deep copy with `version + 1`. The input is never mutated.
- `version` persists in `threads.incident_draft` (JSON), added in Step 3. `reports` does not carry it, so there is one home.
- `set_policy_fields` is the only writer for `capture_state` and `routing_status`, so `verified` has an owner. It validates the enums and requires a reason.

---

## Tests

`code/test_graph_schemas.py`, `unittest`, offline, no temp files.

Shape and enums:

- every enum is a tuple of unique non-empty strings;
- the annotation sets of `IncidentDraft`, `ThreadState` and `ExecutedOutcome` match the contract lists, so a later step cannot silently drop a field;
- valid plans for log, ask, answer and escalate pass;
- unknown `dialogue_act`, `action`, `fit`, `routing_status`, `transport` and `severity` are rejected;
- unknown keys at case, expect, plan, specialist result and bubble level are rejected;
- ask with zero or two clarifications is rejected; ask with a clarification on a log action is rejected;
- answer without `fact_request` is rejected;
- a model plan with `emergency_999` is rejected;
- a specialist `supported` with empty `source_refs` or `fact_ids` is rejected; a source date in 2030 is rejected; a non-http URL is rejected;
- mismatch with no observations is rejected;
- a bubble plan with 0, 4, a URL in text, `www.`, markdown, an em dash, an en dash, a report id or 301 characters is rejected;
- `url="/council"` and a URL without an `/r/<token>` path are rejected;
- a suppressed plan is accepted only with `allow_suppressed=True`.

Patch:

- patch is `None`, `{}`, flat, or has an unknown key: rejected, draft unchanged;
- unknown key inside `set`, `add` or `clear`: rejected;
- `set.description=""`, `set.attachments=[]`, `set.evidence=[...]`, `set.location.street=""`: rejected;
- `set.retracted`: rejected; `add.attachments` appends and dedupes by ref;
- `clear` with no reason or a junk reason: rejected; clearing description, evidence, attachments or a filled location: rejected;
- clearing `location` holding `"Not given"`, `"not given"` or `"  Not given "`: all allowed with a reason;
- stale version: rejected, original returned; no-op patch: `patch.no_change`, version unchanged;
- a successful patch returns a new draft with `version + 1` and passes `validate_incident_draft`;
- `set_policy_fields` is the only way to set `capture_state` or `routing_status`.

Isolation:

- `state.py`, `schemas.py`, `copy_rules.py` and `__init__.py` import no project module and no third party;
- `copy_rules` patterns match `voice.py`'s, asserted directly.

---

## Verification

```bash
python code/test_graph_schemas.py
cd code && python -m unittest discover -p "test_*.py"
python code/eval/messages.py
git status --short
```

Acceptance:

- `python code/test_graph_schemas.py` passes.
- The full suite is 483 plus the new tests, all green.
- `python code/eval/messages.py` stays 31/31.
- No production file outside `code/graph/` and the new test is changed.
- D51 (capture and routing columns) and D57 (keep the data and capability layer) are recorded in `DECISIONS.md` before the commit.
- One commit: `Add graph state and schema contracts`.

---

## What this step does not do

- No graph, no nodes, no checkpointer.
- No database, no `reports` columns. Storage is Step 3, including `threads.incident_draft` for the version.
- No policy. Step 4 checks fact-sheet allowlists, category membership, claim permissions and budget.
- No model call. Step 7 asks the model for a TurnPlan.
- No resident-page truth fix. D55 owns `resident.html` and `website.STEPS`, and Step 10 carries it.
- No change to `triage.normalise`, which still serves the legacy path until cutover.

---

## Doctor findings carried into later steps

These are real and are recorded here so they are not lost:

- Step 1 harness: fixed in `6b92eb8` (retraction verdict, restart memory, unverified labels, global never-said guard, known-key whitelist, drained queue).
- Step 0 major: `resident.html` and `website.STEPS` still claim council receipt. D55 moves into Step 10 with a test.
- Step 0 minor: `messages.greeting` says "I will log it with the council", and `tools.STATUS_TEXT` says "being looked at by the council". Both go into the Step 10 truth pass.
- Oracle: the trajectory runner must become the gate at Step 6/10/12; cutover needs a test and eval migration step; D53 must be signed before Step 6; safety and never-saved fixtures must be added before the graph is judged.
- Evidence: `PHOTO_ASK`, the trunk-road line and the tree `alternate: cleansing` need correction or sourcing before they are spoken again.

# Step 4: policy

Scope: one step, one commit. Pure functions. No I/O, no model, no database, no agent imports. Implemented after the oracle and reviewer audits; this file records the final contract.

Parent plan: `plans/BUILD-STEPS.md`, Step 4. Architecture: `plans/IMPLEMENTATION_PLAN.md`, sections 2, 3, 8 and 11.

---

## Context

The schema layer now guarantees that a plan is well formed. It does not guarantee that the plan is allowed. A perfectly shaped plan can still log a utility problem, ask for a street the resident already gave, retract a claim that was never sent, or claim council receipt.

This step is the deterministic gate between the model's proposal and any write. It is the place where the reported failure is finally prevented in code, not in prose.

The Step 4 plan was audited by two background subagents before implementation. The oracle built bad plans the policy would wrongly allow and good plans it would wrongly block. The reviewer checked the API, the repair split and the tests. Their blocking findings are recorded below and are in the code.

---

## Audit fixes applied

- `check` applies `incident_patch` through `schemas.apply_patch` and judges the effective draft. A plan can no longer smuggle a forbidden category or a cleared location past the gate.
- `ThreadState` gains `emergency` and `model_calls`. `short_circuit` now means a cheap turn (greeting, status, silence), not an emergency. An emergency may answer or escalate, never log, ask or patch. A suppressed turn returns no violations.
- `check(state, context, problems=())` accepts the schema problem strings Step 7 already has, and `violation_from_problem` converts them. A missing or non-dict plan is a hard `policy.plan_missing`, never an exception.
- The violation dict keeps `hard`, and `schemas.VIOLATION_KEYS` now allows it, so a violation can round-trip through `validate_thread_state`.
- `known_facts` maps URL to the CSV date. A correct URL with a wrong date is `policy.fact_date` (hard).
- `check_bubbles` enforces `claim.council_receipt`, `claim.timescale`, `claim.number` and `claim.team` over the writer's text. Step 9's lint is still the full copy gate.
- New semantic checks: `policy.specialist_mismatch`, `policy.routing_unverified`, `policy.question_repeated`, substantive correction, both the effective and proposed category, and a denial cannot be retracted as a claim.
- `capture.lost` for a log is separate from `capture.no_location` on an outcome, and a fresh ask for a description is allowed.
- The hard/repairable tables cover every `schemas.PROBLEM_CODES` entry plus the policy codes; deferred copy and duplicate codes are listed in `DEFERRED` with an owner.

---

## Files

Implemented:

```text
code/graph/policy.py
code/test_graph_policy.py
code/graph/state.py            emergency and model_calls
code/graph/schemas.py          VIOLATION_KEYS includes hard
code/test_graph_schemas.py     the violation round-trip test
plans/STEP-04-policy.md
```

Not touched: `code/graph/{store,copy_rules}.py`, `code/agents/`, `code/tools.py`, `agent/`.

---

## API

```python
@dataclass(frozen=True)
class PolicyContext:
    known_categories: frozenset[str] | None = None
    category_outcomes: Mapping[str, str] | None = None
    known_facts: Mapping[str, str] | None = None          # url -> date_checked
    allowed_destinations: frozenset[str] | None = None
    allowed_questions: frozenset[str] | None = None
    allowed_numbers: frozenset[str] | None = None
    forbidden_team_names: frozenset[str] | None = None
    missing_fields: frozenset[str] | None = None
    handoff_categories: frozenset[str] = frozenset(
        {"noise_nuisance", "other_nuisance", "property_concern"})
    never_saved: frozenset[str] = frozenset(
        {"outside_southampton", "not_council_trunk_road", "not_council_utility"})

def check(state, context=PolicyContext(), problems=()) -> list[dict]
def violation_from_problem(problem) -> dict
def check_outcome(outcome, draft=None, context=PolicyContext()) -> list[dict]
def check_bubbles(bubbles, outcome=None, context=PolicyContext()) -> list[dict]
def can_repair(violations) -> bool
def hard_failures(violations) -> list[dict]
def decide(violations, repair_count=0) -> "execute" | "repair" | "fallback"
```

A violation is `{"code": str, "field": str | None, "message": str, "hard": bool}` and `schemas.VIOLATION_KEYS` accepts it.

`None` in a context field means "not checked here". Step 5 builds the real categories and fact mapping into the playbooks; Step 6 injects them; Step 7 supplies the escalation destinations.

---

## Rules

### Capture and category

- A `log` or `ask` with no description and no attachment is `capture.lost` (hard). A photo with no words is still capturable.
- `unclear_other` is always an allowed category. That is what makes capture-first possible when classification is wrong.
- If `known_categories` is supplied, any other candidate must be in it; otherwise `policy.category_unknown` (repairable to `unclear_other`).
- If the category is in `never_saved`, `not_council.saved` (hard). This covers outside Southampton, trunk roads and utilities.
- If `category_outcomes` says `not_council`, `not_council.saved` (hard).
- If the category is in `handoff_categories` (noise, other nuisance, property), a `log` is `policy.handoff_action` (repairable to `escalate` or `answer`). D48: nothing is saved for a neighbour's home.
- An `info_only` category is never logged directly. The capture step maps it to `unclear_other`; a plan that logs `flooding_severe_weather` itself is `policy.category_unknown`.

### Questions

- `action="ask"` for `location` when the draft already has a street or address is `ask.known_field` (repairable).
- `action="ask"` for `description` when the draft already has words is `ask.known_field`.
- If `allowed_questions` is supplied and the target is not in it, `policy.question_unknown` (repairable).
- A question for a field that is genuinely missing is allowed, including `location` when the draft holds only `"Not given"`.

### Corrections and claims

- `dialogue_act="challenge_previous_claim"` requires non-empty `retracted_claims`. With no `last_claims_sent`, `retraction.missing` is hard: there is nothing to retract, so the turn falls back rather than pretending.
- With `last_claims_sent`, every retracted claim must appear in one of those claims (case-insensitive substring). Otherwise `retraction.missing` (repairable: name the claim that was actually sent).
- `dialogue_act="correction"` with an empty patch is `policy.correction_noop` (repairable). A correction that changes nothing has not corrected anything.
- A challenge never requires a category change. The incident is preserved.

### Answers and escalation

- `action="answer"` with `fact_request.category_id` outside `known_categories` is `policy.category_unknown`.
- `action="escalate"` with a destination outside `allowed_destinations` is `policy.destination_unknown` (hard). A model cannot invent a URL or a phone number.
- `emergency_999` is allowed only when `state["short_circuit"]` is true. Elsewhere it is `escalation.emergency_from_model` (hard), duplicating the schema guard because this is safety-critical.
- A short-circuit turn may not log, ask or patch: `emergency.tools` (hard). It answers or escalates and stops.

### Budgets

- `repair_count > 1` is `budget.exceeded` (hard).
- `specialist_call_count > 2` is `budget.exceeded`.
- A `specialist_request` when `specialist_call_count >= 2` is `budget.exceeded`.
- More than two `specialist_results` is `budget.exceeded`.

### Outcome

`check_outcome` runs after execute, before the writer.

- `submitted=True` is `claim.council_receipt` (hard). Phase 1 has no submission integration.
- `locally_actionable=True` while the draft has no street (or only `"Not given"`) is `capture.lost` (hard).
- Every fact URL must be in `known_fact_urls` when supplied; otherwise `policy.fact_unknown` (hard).
- `saved=True` with no report is a schema problem; the policy repeats it defensively.
- A failed or ambiguous transport must keep its error; the writer reads it. Policy does not rewrite it.

### Repair decision

```python
REPAIRABLE = {
    "schema.invalid", "ask.known_field", "ask.multiple_targets",
    "policy.category_unknown", "policy.correction_noop",
    "policy.not_council_action", "policy.handoff_action",
    "policy.question_unknown", "retraction.missing",
}
HARD = {
    "capture.lost", "not_council.saved", "emergency.tools",
    "budget.exceeded", "claim.council_receipt",
    "policy.fact_unknown", "policy.destination_unknown",
}
```

- No violations: `execute`.
- Any hard violation: `fallback`.
- Only repairable violations and `repair_count < 1`: `repair`.
- Otherwise: `fallback`.

A hard violation cannot be repaired into a write. The fallback must still preserve the draft.

---

## Effectiveness map

This table is the check the oracle will run. Each row is a failure the product has already seen or the plan requires.

| Failure to prevent | Rule | Test |
|---|---|---|
| A wrong category erases a real report | `unclear_other` always allowed; `capture.lost` only when there is no evidence | `test_capture_with_unclear_other_is_allowed` |
| A utility or outside-Southampton report is saved | `not_council.saved` | `test_never_saved_categories_are_refused` |
| A neighbour's home is saved | `policy.handoff_action` | `test_handoff_must_not_log` |
| The bot asks for a street already given | `ask.known_field` | `test_ask_cannot_repeat_a_known_location` |
| A challenge is answered with a generic link | `retraction.missing` forces a named retraction | `test_challenge_without_claims_is_refused` |
| A challenge retracts something never said | matching against `last_claims_sent` | `test_challenge_claim_must_match_what_was_sent` |
| A correction changes nothing | `policy.correction_noop` | `test_a_noop_correction_is_refused` |
| A local save claims council receipt | `claim.council_receipt` on `submitted` | `test_submitted_outcome_is_refused` |
| An emergency writes or patches | `emergency.tools` | `test_an_emergency_cannot_write` |
| A model invents a destination or a fact | `policy.destination_unknown`, `policy.fact_unknown` | `test_destination_and_fact_allowlists` |
| The repair or specialist loop runs away | `budget.exceeded` | `test_budget_exhaustion_falls_back` |
| A valid capture is blocked by the policy | no rule rejects `unclear_other`, `needs_review` or a missing street | `test_a_captured_incident_passes` |

If a row cannot be tested with the policy alone, the plan says which later step owns it. A terminal generic link, for example, is a writer-lint rule in Step 9, not a policy rule.

---

## Tests

`code/test_graph_policy.py`, `unittest`, offline, no temp files.

- a captured `unclear_other` log at `"Not given"` passes;
- a log with no description and no photo is `capture.lost`;
- a photo-only capture passes;
- `outside_southampton`, `not_council_trunk_road` and `not_council_utility` are `not_council.saved`;
- an `info_only` category logged directly is `policy.category_unknown`;
- a handoff category logged is `policy.handoff_action`;
- asking for a known location or a known description is `ask.known_field`;
- asking for location when the draft holds `"Not given"` is allowed;
- an unknown question target is `policy.question_unknown` when the allowlist is supplied;
- a challenge with no claims and no sent claims is hard `retraction.missing`;
- a challenge whose claim is not in `last_claims_sent` is repairable `retraction.missing`;
- a matching challenge passes and does not require a category change;
- a no-op correction is `policy.correction_noop`;
- an escalation destination outside the allowlist is hard `policy.destination_unknown`;
- `emergency_999` without `short_circuit` is hard;
- a short-circuit emergency with a log, ask or patch is `emergency.tools`; with an answer or escalate it passes;
- `repair_count=1` plus a repairable violation decides `fallback`; `repair_count=0` decides `repair`;
- `specialist_call_count=2` plus a specialist request is `budget.exceeded`;
- `check_outcome`: `submitted=True` is `claim.council_receipt`; `locally_actionable` without a street is `capture.lost`; an unknown fact URL is `policy.fact_unknown`; a clean outcome passes;
- `decide` returns `execute`, `repair` or `fallback` for clean, repairable and hard sets;
- `policy.py` imports only `dataclasses`, `typing` and `graph.state`; no model, database, network or `agent/`.

---

## Verification

```bash
python code/test_graph_policy.py
cd code && python -m unittest discover -p "test_*.py"
python code/eval/messages.py
git status --short
```

Acceptance:

- `python code/test_graph_policy.py` passes, 57 tests.
- The full suite is 595 tests, 4 skips, all green.
- `python code/eval/messages.py` stays 31/31.
- The changed production files are `code/graph/policy.py`, `code/graph/state.py` and `code/graph/schemas.py`, with their tests.
- One commit: `Add the graph policy gate`.

---

## What this step does not do

- No graph nodes. Step 6 wires `validate` to `check`.
- No facts or playbooks. Step 5 builds categories and `known_facts` into the playbooks; Step 6 injects them.
- No full copy lint. Step 9 owns bubbles, markdown, URLs and the template fallback; `check_bubbles` is the claim gate here.
- No execution. Step 8 performs the write `check` approved.
- No human review queue. Step 10 owns the fallback route.
- No category inference. The policy judges the plan it is given; it does not classify.
- `duplicate.unverified` is raised at Step 8 when `duplicate_of` is set without a verified check.

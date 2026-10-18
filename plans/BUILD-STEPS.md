# Build steps: LangGraph rebuild

This is the execution plan. The architecture and contracts live in `plans/IMPLEMENTATION_PLAN.md`. This file is the sequence you review, one small step at a time.

Status: **Step 0 only, for approval.** Steps 1 to 13 are a roadmap and are not authorised by this approval. Each later step is approved separately, after the previous one is accepted.

The three capture and truth fixes are in the working tree and tested. No graph code exists yet.

---

## Context

The current runtime is one pass with no durable conversation state. A wrong category used to erase a report, a correction could not attach to anything, and the writer rephrased the intended action. The three fixes landed at 01:33 changed the decisions, not the architecture.

This build replaces the decision and runtime layer with one LangGraph `StateGraph`, a checkpointer, typed plans, a deterministic policy gate, a writer bound to executed outcomes, and an outbox. The facts, categories, geo, pin service, database, dashboard and tested agent capabilities stay as libraries.

Build slowly: one step, one commit, full suite green, then review. No step begins before the previous one is accepted.

## Approval gate

Approving this plan authorises **Step 0 only**: freeze the current working tree.

After Step 0 I stop and report the commit hash, the suite result and the evaluation result. Step 1 is submitted for approval separately. No file in `code/graph/`, `code/services/` or `code/specialists/` is created until Step 1 is approved.

| Step | Scope | Approval |
|---|---|---|
| 0 Freeze | commit the three fixes, record the baseline | **this approval** |
| 1 Trajectories | 8 fixtures and their loader | next |
| 2 Contracts | state, schemas, patch semantics | later |
| 3 Store | threads, outbox, turn operations | later |
| 4 Policy | deterministic invariants | later |
| 5 Playbooks | 22 generated playbooks | later |
| 6 Graph shell | hydrate, precheck, cheap, capture | later |
| 7 Decide | decide, validate, repair | later |
| 8 Execute | execute, brief, single write path | later |
| 9 Writer | bubbles, lint, outbox | later |
| 10 Corrections | retraction and restart | later |
| 11 Cutover | both channels on the graph | later |
| 12 Specialist | highways subgraph, optional | later |
| 13 Cleanup | remove legacy, rehearse | later |

---

## Approach

1. Freeze the expected behaviour as trajectory fixtures before any graph code.
2. Build the contracts, store and policy as pure, testable modules with no LangGraph dependency.
3. Generate playbooks from `agent/` so they cannot drift.
4. Assemble the graph shell, then add nodes one edge at a time.
5. Cut the channel over only after the graph runs the same turn as the legacy path.
6. Add one specialist subgraph, then promote others only on measured failure (D60).

Each step is small enough to review as a single diff, ideally under 400 changed lines.

---

## Files to modify

New:

```text
code/graph/__init__.py
code/graph/state.py
code/graph/schemas.py
code/graph/store.py
code/graph/policy.py
code/graph/nodes.py
code/graph/build.py
code/graph/runtime.py
code/graph/writer.py
code/services/build_playbooks.py
code/services/playbooks/*.yaml
code/services/reports.py
code/specialists/base.py
code/specialists/registry.py
code/specialists/highways.py
code/eval/trajectories/cases.json
code/test_graph_schemas.py
code/test_graph_store.py
code/test_graph_policy.py
code/test_playbooks.py
code/test_graph_runtime.py
code/test_graph_decide.py
code/test_graph_execute.py
code/test_graph_writer.py
code/test_graph_corrections.py
code/test_specialists.py
code/test_trajectories.py
```

Changed, only in the step that names them:

```text
code/reports_db.py        Step 8, the single write path and additive migrations
code/tools.py             Step 8, save_report delegates to the new writer
code/blue_bubbles.py      Step 11, MODE=graph
code/simulator.py         Step 11, MODE=graph
code/requirements.txt     Step 6, langgraph pins
```

Not touched: `agent/`, `code/geo/`, `code/pin/`, `code/web/`, `dashboard/`, `info/`, `reference/`.

---

## Reuse

| Need | Use |
|---|---|
| Facts, categories | `agent/loader.py`, `tools._rulebook()`, `tools.find_category_facts()` |
| Report write, token, duplicate re-check | `tools.save_report`, `reports_db.connect`, `BEGIN IMMEDIATE` |
| Location | `agents/location_agent.py`, `code/geo/`, `pin_service.py` |
| Safety words | `triage.EMERGENCY_WORDS`, `agents/safety.py` |
| Duplicate candidates | `agents/duplicate.py`, `tools.check_duplicate` |
| Photo features | `agents/photo.py`, `photo_features.py` |
| Copy fallback | `messages.py`, `voice.lint` |
| Status updates | `agents/status.py`, `website.STATUS_HOOKS` |
| Test fixture pattern | `test_agents.AgentCase.setUp` |
| Dashboard | `website.py`, `web/templates/` |

---

## Subagent rules

- One writer per tree. A worker owns only the files listed in its step. Do not let two writers run at once.
- Parallel children are `scout`, `reviewer`, `oracle` or `evidence-auditor`, all read-only.
- Before each step, one `scout` confirms the seam and returns file:function, not prose.
- After each step, one `reviewer` reads the diff against this file and returns a verdict. The parent applies fixes.
- Any factual string gets `evidence-auditor`: the CSV row, URL and date.
- Any conflict with `DECISIONS.md` gets `oracle` before code.
- Each step ends in one commit. Full suite green. No step stacks on a red suite.

---

## Steps

Only Step 0 is in scope for this approval. Steps 1 to 13 stay here as the roadmap, not as authorisation.

### [ ] Step 0. Freeze the starting point (10 minutes)

Goal: make the current working tree the baseline the graph is built on.

Actions:
1. Read `git diff` for the three fixes and confirm it matches the worklog entry at 01:33.
2. Commit the three fixes and the documentation changes as one commit: `Capture first: keep a real report when the category is info_only or unknown`.
3. Record the commit hash, the unit-test count and the evaluation count in a new `WORKLOG.md` line.
4. Change no code, no decision number and no plan file.

Done when:
- `git status` is clean.
- `cd code && python -m unittest discover -p "test_*.py"` reports 475 passing.
- `python code/eval/messages.py` reports 31/31.
- The commit hash is in the worklog.

Stop after this. Do not start Step 1.

---

## Roadmap, not yet approved

Each step below is submitted for approval after the previous one is accepted. Nothing in this section is authorised by the current approval.

### [ ] Step 1. Trajectory fixtures (worker + reviewer, 45 minutes)

Files: `code/eval/trajectories/cases.json`, `code/test_trajectories.py`.

Eight cases: tree capture, challenge and retraction, wrong specialist, null patch, photo after text, two incidents, duplicate webhook, restart.

Each case records turns, expected rows, required and forbidden reply strings, and whether legacy passes today. Legacy is expected to fail the correction and restart cases.

Done when: `python code/test_trajectories.py` loads 8 cases, asserts their shape, and asserts today's legacy status. No production file changes.

Review focus: are the expectations truthful and specific enough to fail a bad graph?

### [ ] Step 2. Contracts (worker + reviewer, 2 hours)

Files: `code/graph/__init__.py`, `code/graph/state.py`, `code/graph/schemas.py`, `code/test_graph_schemas.py`.

`ThreadState`, `IncidentDraft`, `TurnPlan`, `SpecialistResult`, `ExecutedOutcome`, `BubblePlan`, enums, and `apply_patch` with set/clear/omit.

Done when: enum, schema and patch tests pass offline. A null field cannot clear location, description or evidence. No LangGraph import.

Review focus: patch semantics and enum validation. This contract is what every later step trusts.

### [ ] Step 3. Store and migrations (worker + reviewer, 1.5 hours)

Files: `code/graph/store.py`, `code/test_graph_store.py`.

`migrate()`, `ThreadStore`, `Outbox`, `TurnOperations` over `sqlite3`. Tables exactly as in the architecture plan, section 6. Temp database per test.

Done when: migration is idempotent, pending question round-trips, outbox orders by `seq`, `operation_key` is unique, `turn_operations` returns a recorded result.

Review focus: SQL and concurrency. WAL and busy timeout must match `reports_db.connect`.

### [ ] Step 4. Policy (worker + reviewer, 1.5 hours)

Files: `code/graph/policy.py`, `code/test_graph_policy.py`.

Pure functions returning violation dicts with the codes listed in the architecture plan. No I/O.

Done when: every violation code has one passing and one failing test. Hard failures and repairable failures are separated.

Review focus: no false pass. A plan that claims council receipt must never validate.

### [ ] Step 5. Playbooks (worker + reviewer, 1.5 hours)

Files: `code/services/build_playbooks.py`, `code/services/playbooks/*.yaml`, `code/test_playbooks.py`.

Generate one YAML per category from `categories.json` plus the CSV. Include `version`, `facts`, `required_local`, `required_submission`, `questions`, `form_url`, `source_url`, `source_date`, `dup_window_days`, severity rules.

Done when: 22 files, deterministic regeneration, `--check` exits 0, every fact has a URL and date.

Review focus: no invented requirement. If the source does not say it, the playbook does not contain it.

### [ ] Step 6. Graph shell (worker + reviewer, 2 hours)

Files: `code/graph/nodes.py` (hydrate, precheck, cheap, capture), `code/graph/build.py`, `code/graph/runtime.py`, `code/test_graph_runtime.py`, `code/requirements.txt`.

Install and pin `langgraph` and `langgraph-checkpoint-sqlite`. Deps injected. `MemorySaver` in tests.

Done when: `python code/graph/runtime.py --turn "there is a tree fallen on the road"` with a fake model writes one capture row and shows the decision. Emergency short-circuits with zero model calls. No channel changes.

Review focus: dependency injection, no module-level globals, and the precheck order.

### [ ] Step 7. Decide, validate, repair (worker + reviewer, 2 hours)

Files: `code/graph/nodes.py`, `code/test_graph_decide.py`.

Central decision call, `TurnPlan` validation, one repair, fallback. `ask` persists one clarification target.

Done when: log, ask, answer and escalate each pass. An invalid plan is repaired once, then falls back. Budget counters are respected.

Review focus: the model cannot choose a write; it proposes, policy decides.

### [ ] Step 8. Execute, brief, single write path (worker + reviewer, 2 hours)

Files: `code/services/reports.py`, `code/graph/nodes.py` (execute, brief), `code/reports_db.py`, `code/tools.py`, `code/test_graph_execute.py`.

Move the insert into `reports_db.create_report`. `tools.save_report` delegates. Add `capture_state` and `routing_status`. Idempotency through `turn_operations`.

Done when: one row per turn, replay returns the recorded result, token minted once, no council receipt, `capture_state` correct.

Review focus: one write path, no second schema, no lost duplicate check.

### [ ] Step 9. Writer, lint, outbox (worker + reviewer, 2 hours)

Files: `code/graph/writer.py`, `code/graph/nodes.py` (compose, lint, enqueue), `code/graph/store.py`, `code/test_graph_writer.py`.

Writer reads `ExecutedOutcome`, not the plan. Lint checks claims and copy. Template fallback. Outbox words then link.

Done when: 1 to 3 bubbles, one URL, local save never claims receipt, failed send recorded as failed or ambiguous, ordering preserved.

Review focus: every claim is traceable to the outcome or a fact.

### [ ] Step 10. Corrections and restart (worker + reviewer, 1.5 hours)

Files: `code/graph/nodes.py` (hydrate, reconsider), `code/test_graph_corrections.py`.

Persist claims, detect a challenge deterministically, retract, preserve the incident, resume the pending question. Restart test with `SqliteSaver`.

Done when: the tree trajectory passes, one row, retraction recorded, pending question survives a new runtime instance.

Review focus: correction cannot create a second report, and cannot delete evidence.

### [ ] Step 11. Channel cutover (worker + reviewer, 1 hour)

Files: `code/blue_bubbles.py`, `code/simulator.py`, `code/test_bot.py`.

`MODE=graph` calls `TurnRuntime`. `MODE=legacy` keeps the old path. Delivery drains the outbox.

Done when: the same input produces the same rows and bubbles through the webhook and the simulator. Legacy still runs behind the flag.

Review focus: guards preserved: self-ignore, stale skip, GUID dedupe, burst, one turn per sender.

### [ ] Step 12. First specialist (worker + reviewer, 1.5 hours, optional before freeze)

Files: `code/specialists/base.py`, `code/specialists/registry.py`, `code/specialists/highways.py`, `code/test_specialists.py`.

Highways first: pothole depth bands, abandoned vehicle duration, parking obstruction. One model call maximum. Returns `fit`.

Done when: supported, uncertain and mismatch each pass, and a mismatch preserves the draft and reroutes once.

Review focus: the specialist changes a recommendation, not a label.

### [ ] Step 13. Cleanup and rehearsal (owner + reviewer, 45 minutes)

- Delete the legacy orchestrator only after the trajectory suite is green.
- Update `CLAUDE.md`, `WORKLOG.md`, `NUMBERS.md`, and the README's AI-generated section.
- Run the demo path end to end and the failure case.

Done when: `MODE=legacy` is removed, the suite is green, and the demo runs without edits.

---

## Verification

After every step:

```bash
cd code && python -m unittest discover -p "test_*.py"
python code/eval/messages.py
```

After Step 6:

```bash
python code/graph/runtime.py --turn "there is a tree fallen on the road"
```

After Step 10:

```bash
python code/graph/runtime.py --selftest
```

After Step 11:

```bash
python code/simulator.py
```

Manual checks: one tree message captures one row and asks once; a challenge retracts without a second row; a pothole with a street saves and says it has not gone to the council; an emergency writes nothing and calls no model; a restart keeps the pending question.

---

## Open items

- D51 to D57 are signed one line at a time, in the step that needs them: D51 at Step 3, D52 and D55 at Step 10, D53 at Step 11, D54 at Step 1, D56 at Step 3, D57 before Step 2. No decision number changes in Step 0.
- LangGraph install happens in Step 6, with its own approval. If it fails on the demo machine, stop and report.
- One commit per step. If a step passes 400 changed lines or two hours, stop and split it.
- If a playbook group fails its trajectory slice after Step 12, use the D60 promotion rule. Two promotions maximum.

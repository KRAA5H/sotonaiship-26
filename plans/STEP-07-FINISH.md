# Step 7: finish the graph (one combined plan)

Status: single execution plan for all remaining work. Supersedes Steps 7 to 13 in `plans/BUILD-STEPS.md`. One approval, five internal phases, one combined doctor per checkpoint.

Current state, 18 Oct 04:20:
- HEAD `51d6e7c`. 645 tests, 4 skips, 31/31 message evaluation. Tree clean.
- Steps 0 to 6 done: capture and truth fixes, trajectory fixtures, contracts, storage, policy, playbooks, graph shell.
- The Step 6 doctor found and closed two blocking shell bugs: a duplicate replay no longer wipes thread memory, and the live `photo_ref` tuple is stored as `guid:<id>`. `hydrate` now starts from `new_thread_state`, so P1's counters exist. The inherited 999 false positive on `fire station` is fixed; `fire` and `trapped` need hazard or person context.
- `code/graph/` has `state, schemas, store, policy, copy_rules, nodes, build, runtime`.
- The shell hydrates, prechecks danger and empty input, handles silence and greetings, and captures a provisional draft. `--turn` writes no report row. `--selftest` passes.
- `blue_bubbles.py` and `simulator.py` still call the legacy `ORCHESTRATOR`. No decide, write, writer, outbox drain, corrections or channel cutover yet.
- LangGraph `1.2.16` and `langgraph-checkpoint-sqlite 3.1.2` installed and pinned.
- The Step 6 goal doctor is running. Its findings are folded before Phase 1.

Submission locks 13:00. Do not add scope.

---

## Goal contract

| Goal | Phase | Proof |
|---|---|---|
| Natural texting: casual, Gen Z-ish, short separate DMs | P3 | Writer bubbles from the executed outcome; `voice.lint`; template fallback; a style test with no two identical replies |
| Actually finish tasks | P1-P3 | Tree conversation creates one row and a link without restarting |
| One LangGraph orchestrator | P5 | Both simulator and webhook call `TurnRuntime`; legacy behind `MODE=legacy` |
| Useful specialists | Deferred | D60: playbooks only, no specialist subgraph before the freeze |
| Conversation memory | P4 | Pending question and last claims survive a new runtime instance |
| Messy input: text, photos, pins, bursts | P2-P4 | Photo-only capture, shared pin location, burst handled as one turn |
| No classification trap | P1 | A wrong category is repairable or falls back to `unclear_other`; the draft survives |
| Ask less | P1 | Policy blocks a known field and a repeated pending question |
| Recover naturally | P4 | The tree challenge retracts flooding, keeps the row, asks once |
| Concrete action | P2-P3 | Log, ask, answer, escalate; no generic link as a terminal action |
| Truthful and safe | P3-P4 | Local save never claims receipt; fact URL and date; emergency no tools |
| Usable outcomes | P2 | Located, structured, de-duplicated row with a private link |
| Prove it works | P4-P5 | Trajectory suite runs the graph; full suite and message eval green |
| Use repo evidence | All | Playbooks, facts, geo, schema, exact category list |
| Future phase | Boundary | No permits, challenges or submissions |

---

## Graph after this plan

```text
START -> hydrate -> precheck
precheck -> END                      suppressed, emergency
precheck -> cheap
cheap -> END                         silence, greeting
cheap -> capture
capture -> decide
decide -> validate                   no specialist subgraph in this plan
validate -> repair -> decide         once, when repairable
validate -> fallback                 hard failure, or repair already used
validate -> execute                  clean
execute -> brief -> compose -> lint -> enqueue -> END
```

No specialist node. The playbook and `Deps.playbooks` are still injected; `specialist_request` is ignored in this plan. D60 keeps the door open after the freeze.

---

## Phase 1: decide, validate, repair (done by 06:30)

Files: `code/graph/prompts.py`, `code/graph/nodes.py`, `code/graph/build.py`, `code/graph/runtime.py`, `code/test_graph_decide.py`, `code/test_trajectories.py`.

- `Deps.llm` is now used. `TurnRuntime` passes `deps.llm` and increments `model_calls` on every call.
- `decide` builds a compact brief: the draft, recent messages, pending question, last claims, the playbook for every candidate, and the four allowed actions. It asks for one JSON TurnPlan and validates it with `schemas.validate_turn_plan`.
- Capture-first rule in the prompt: a physical problem is never `not_council` and never dropped; if the category is unsure, use `unclear_other`, action `log`, and ask one question.
- One repair: schema problems and repairable policy violations go back to `decide` once with the violations. Hard violations go to `fallback`.
- `fallback` preserves the draft:
  - repairable category problem: capture as `unclear_other`, action `log`;
  - `capture.lost`: ask for the problem or a photo;
  - `not_council.saved` or a bad destination: escalate to an official destination;
  - ungrounded answer: answer from the checked fact sheet or ask.
- Policy context from the index: categories, outcomes, handoff and never-saved sets, fact URLs and dates, allowed questions per category, required local fields, location mode, allowed numbers and destinations, forbidden team names.
- Tests: log, ask, answer, escalate; tree capture with an `info_only` model answer; unknown category fallback to `unclear_other`; one repair then fallback; answer with no facts refused; ask a known field; challenge without claims; model failure degrades safely; `model_calls` capped at 4.

Done when: the tree message through the graph yields action `log`, service `unclear_other`, one question, and no report row yet (write is P2).

---

## Phase 2: execute, single write, early graph demo (done by 08:30)

Files: `code/services/reports.py`, `code/graph/nodes.py` (execute, brief), `code/reports_db.py`, `code/tools.py`, `code/simulator.py`, `code/test_graph_execute.py`, `code/test_simulator.py`.

- One write path: `reports_db.create_report(...)` is the only insert. `tools.save_report` delegates to it. `turn_operations` makes `(turn_id, "commit")` idempotent.
- `execute` handles the four actions:
  - `log`: resolve location, check duplicates, insert one row with `capture_state` and `routing_status`, mint the token once;
  - `ask`: persist the pending question and update the draft, no row;
  - `answer`: use `rag.answer` and the checked facts, no row;
  - `escalate`: use the playbook guidance, no row.
- `brief` builds `ExecutedOutcome` from what actually happened, including `saved`, `report_id`, `link_token`, `missing`, `facts`, `review_queued`, `transport`, `degraded` and `playbook_version`.
- `simulator.py` gets `MODE=graph` and calls `TurnRuntime` for the tree and a pothole, while the webhook stays on `MODE=legacy`. This is the early graph demo checkpoint.
- Tests: one row per turn; replay does not duplicate; token once; local save never `submitted`; captured `unclear_other` at `"Not given"`; a pothole with a street; duplicate link; simulator graph turn.
- A replay older than `last_turn_id` is not caught by the shell; `turn_operations (turn_id, commit)` is the write guard. Keep it in this phase.
- The normalized `photo_ref` (`guid:<id>`) feeds `has_photo`; do not re-parse the raw tuple.

Done when: the simulator creates one row and returns a private link for the tree and a pothole, and `SELECT COUNT(*)` proves no duplicate on replay.

**Cut line 1:** if Phase 2 is not green by 08:30, drop P3 to templates, keep the graph write and the simulator demo, and go straight to P4. Do not return to the legacy path for the demo.

---

## Phase 3: writer, lint, outbox (done by 10:00)

Files: `code/graph/writer.py`, `code/graph/nodes.py` (compose, lint, enqueue), `code/graph/store.py` (outbox methods already exist), `code/test_graph_writer.py`.

- `compose` receives `ExecutedOutcome`, the draft and the playbook facts. It writes 1 to 3 bubbles, one purpose each, casual and short, with contractions and no corporate phrasing.
- It never sees the plan and cannot set the link. The runtime appends the URL. It cannot claim council receipt for a local save, a crew, a timescale, a team or a number not in the index.
- `lint` runs `voice.lint` and `policy.check_bubbles`. On failure, use `messages` templates, then `check_bubbles` again. One truthful rephrase, then the template.
- `enqueue` writes words and link as separate outbox rows, ordered by `seq`, unique by `operation_key`. `claims_sent` records the bubbles that were actually enqueued.
- Tests: local save wording; capture wording; challenge wording; answer with a source; escalation with a destination; no bubble claims receipt; 1 to 3 bubbles; one URL; outbox order; failed and ambiguous send recorded; template fallback.

Done when: the tree, pothole, question, status and escalation turns each produce natural bubbles, and no local save claims council receipt.

---

## Phase 4: corrections, restart, safety (done by 11:15)

Files: `code/graph/nodes.py` (hydrate claims, retraction), `code/eval/trajectories/cases.json`, `code/test_graph_corrections.py`, `code/test_trajectories.py`.

- `hydrate` loads `last_claims` and `pending_question` from `ThreadStore`; `enqueue` updates `last_claims` to the linted bubbles.
- A challenge is detected by the decide prompt or the deterministic regexes. It retracts the named claim, keeps the draft, apologises, and asks the outstanding field once.
- `reconsider` is not a specialist node yet; it applies a corrected patch and resumes.
- Restart test with `SqliteSaver`: a new runtime resumes the pending question and the draft.
- Add four safety fixtures: a question is not captured; an emergency saves nothing; a utility saves nothing; outside Southampton saves nothing. Update the fixture count from 8 to 12.
- The resident-page truth pass is already committed (`ffd64e8`); add a test that `/r/<token>` has no council-officer or council-resolved phrasing.
- Tests: the exact tree challenge (one row, retraction, no generic link); restart; the four safety cases; no second row on a challenge.

Done when: the trajectory suite runs all 12 cases through the graph, and the correction and restart cases pass.

---

## Phase 5: channels, trajectory gate, demo (done by 12:15)

Files: `code/blue_bubbles.py`, `code/simulator.py`, `code/test_bot.py`, `code/test_trajectories.py`, `code/eval/messages.py` (graph path only if time), `plans/STEP-07-FINISH.md`, `WORKLOG.md`.

- `blue_bubbles.handle_inbound` calls `TurnRuntime` under `MODE=graph`; `MODE=legacy` keeps the old path. Keep the self-ignore, stale skip, GUID dedupe, burst coalescing and one-turn-per-sender.
- Delivery drains the outbox: words, then the link, mark `sent`, `failed` or `ambiguous`.
- D56 caveat: the LangGraph checkpoint contains the raw sender. A deletion request must clear the checkpoint as well as the thread row; note it in the delete path even if the demo never exercises it.
- The trajectory suite is the gate: every `layer: graph` case runs, no silent skips.
- The message evaluation runs against the graph only if time allows; otherwise it stays on templates and is migrated after 13:00.
- Keep `test_agents.py` and the legacy path green through the demo. Do not delete the old orchestrator before the freeze.

Done when: one real iMessage and one simulator message both produce the same row and bubbles through the graph, and the tree challenge passes end to end.

---

## Cut and defer, explicitly

- **Step 12, the highways specialist, is cut.** D60 remains the promotion rule after the freeze.
- **The 96 legacy tests and `code/eval/messages.py` are not migrated before the demo.** The legacy path stays available under `MODE=legacy`; the graph has its own tests and the trajectory suite.
- **No new categories.** There is still no tree category; the tree case is `unclear_other` with `needs_review`.
- **No more three-subagent fanout.** One combined doctor at the end of P1, P3 and P5, with the goal table and the tests in the same report.
- **No submission integration.** `submitted` stays false; the resident page already says so.

---

## Checkpoints and clock

| Time | Checkpoint | Gate |
|---|---|---|
| 06:30 | P1 | Tree decide → `unclear_other`, one question, one repair max |
| 08:30 | P2 | Simulator graph: one row, link, no duplicate on replay |
| 10:00 | P3 | Natural bubbles, no receipt claim, ordered outbox |
| 11:15 | P4 | Tree challenge and restart pass; 12 trajectories |
| 12:15 | P5 | Webhook and simulator on the graph; demo rehearsed |
| 12:45 | Freeze | No code edits after this |

If a phase slips, cut P3 to templates, not P2 or P5. If P5 slips, demo on the simulator and keep the webhook legacy; say so plainly.

---

## Verification commands

```bash
python code/graph/runtime.py --selftest
python code/graph/runtime.py --turn "there is a tree fallen on the road"
python code/test_graph_decide.py
python code/test_graph_execute.py
python code/test_graph_writer.py
python code/test_graph_corrections.py
python code/test_trajectories.py
cd code && python -m unittest discover -p "test_*.py"
python code/eval/messages.py
python code/simulator.py
```

---

## What must not be lost

- Capture is never gated by category; `unclear_other` is always allowed.
- One write path, one token, one row; `turn_operations` makes replay safe.
- A local save says it has not gone to the council; no crew, timescale or receipt.
- The policy judges the effective draft after the patch; a candidate cannot kill a capture.
- The playbooks are generated and byte-checked; no invented fact, team or requirement.
- One writer, one doctor per checkpoint, no new scope before 13:00.

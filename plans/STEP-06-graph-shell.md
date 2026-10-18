# Step 6: graph shell

Status: approved and implemented.
Scope: one step, one commit. The runtime shell only. No decision model, no write, no writer, no delivery, no channel change.

Parent plan: `plans/BUILD-STEPS.md`, Step 6. Architecture: `plans/IMPLEMENTATION_PLAN.md`, sections 3 and 5.

---

## Context

The contracts, storage, policy and playbooks now exist as tested libraries. The graph itself does not. This step builds the smallest compiled LangGraph that owns a turn: hydrate the thread, run the deterministic prechecks, handle silence and greetings, and capture a provisional incident draft.

It deliberately stops before the decision agent. Step 7 adds `decide`, `validate` and `repair`; Step 8 adds `execute`; Step 9 adds the writer and outbox. Building the shell first proves the state, checkpointer and dependency injection with no model call and no side effect.

**One correction to the parent plan's done-when.** The parent plan says the shell "writes one capture row". It should not. Writing belongs to Step 8's single write path, because a row created before the category decision would either be orphaned or need a second update path. The shell proves the capture draft and leaves the row to Step 8. The parent plan's done-when is amended in this step.

---

## Files

```text
code/graph/__init__.py
code/graph/nodes.py          hydrate, precheck, cheap, capture
code/graph/build.py          the StateGraph and its edges
code/graph/runtime.py        TurnRuntime, checkpointer, --turn, --selftest
code/test_graph_runtime.py
code/test_trajectories.py    graph runner scaffold, not a silent skip
code/requirements.txt        langgraph pins
DECISIONS.md                 D53
plans/STEP-06-graph-shell.md
```

Not touched: `code/blue_bubbles.py`, `code/simulator.py`, `code/reports_db.py`, `code/tools.py`, `code/agents/`, `agent/`.

---

## Dependencies

```text
langgraph
langgraph-checkpoint-sqlite
```

Install with `pip install langgraph langgraph-checkpoint-sqlite`, pin the exact versions in `code/requirements.txt`, and record them in `WORKLOG.md`. Unit tests use `MemorySaver`; only the runtime CLI and the restart test use `SqliteSaver`. Check the install on the demo Mac before the step; if it fails, stop and report.

D53 is recorded in `DECISIONS.md` before the nodes are written: the LangGraph runtime replaces `TriageAgent` as the decision layer from this step, and D45's "modules, not subgraphs" is superseded for that layer. The channel and the tools remain modules.

---

## Graph

```text
START -> hydrate -> precheck
precheck -> END                  when the input is empty, a duplicate, or suppressed
precheck -> cheap                when the text is silence or a greeting
cheap -> END
precheck -> capture              otherwise
capture -> END
END
```

Step 7 replaces the two `capture -> END` / `cheap -> END` edges with `decide`. The shell has no `validate`, `execute`, `compose` or `enqueue` yet, and no model call.

Nodes:

| Node | Reads | Writes | Side effects |
|---|---|---|---|
| hydrate | inbound, threads | thread_id, turn_id, recent_messages, incident_draft, suppressed | reads the thread store |
| precheck | text, inbound | emergency, short_circuit, suppressed | none; deterministic safety only |
| cheap | text | short_circuit, degraded | none; silence and greeting regexes |
| capture | text, photo refs | incident_draft, candidate_services | none; no row |

`status` is not in this step. A status answer needs the report store and a reply, which belongs with the decision and writer path in Step 7. The shell handles silence and greetings because they are pure and they prove the cheap-turn edge.

---

## State and dependencies

`Deps` is injected into `build_graph(deps, checkpointer=None)`:

```python
@dataclass(frozen=True)
class Deps:
    threads: ThreadStore
    playbooks: dict          # the generated _index.json
    llm: object | None       # unused in Step 6
    now: Callable[[], datetime]
    notifier: Callable | None
    reports: object | None   # unused in Step 6
    outbox: object | None    # unused in Step 6
```

- `thread_id` is the salted `reporter_ref` from `tools.reporter_ref(sender)`, never the raw phone.
- `hydrate` loads `ThreadStore.load(thread_id)`. If there is no row, it calls `new_thread_state(thread_id, turn_id, inbound)`. The runtime saves `last_turn_id`, `incident_draft`, `pending_question` and `last_claims` to `ThreadStore` after each invoke, so duplicate detection and memory survive a new process. It does not write `reports`. It appends the inbound message to `recent_messages`, capped at 12.
- A repeated `turn_id` against `threads.last_turn_id` sets `suppressed=True` and ends the run. The channel keeps its own GUID dedupe until cutover; the graph dedupe is the second guard.
- `precheck` calls `agents.safety.check(text)` for emergency, threat and spam. It sets `emergency=True` and `short_circuit=True`; it does not compose a reply. An empty message sets `suppressed=True`.
- `cheap` uses the existing silence and greeting regexes, copied into `nodes.py` with a comment, so the graph does not import the legacy orchestrator. A greeting sets `short_circuit=True`; a silence sets `suppressed=True`. No model call.
- `capture` calls `new_incident_draft(description=text)`, records `photo_ref` as an attachment reference, sets `capture_state="captured"` and `routing_status="needs_review"`, and leaves `category_id=None`. The decision node in Step 7 chooses the category. No row is written.

`TurnRuntime`:

```python
class TurnRuntime:
    def __init__(self, deps, checkpointer=None)
    def turn(self, inbound) -> dict          # thread_id, turn_id, kind, state
    def selftest(self) -> list[dict]         # scripted turns on MemorySaver
```

`kind` is `"emergency"`, `"silence"`, `"greeting"`, `"captured"`, `"duplicate"` or `"empty"`. `reply` is `None` in this step; the writer is Step 9.

The production checkpointer is `SqliteSaver` in `code/graph.db` (gitignored). The CLI opens it once and compiles one graph.

```bash
python code/graph/runtime.py --turn "there is a tree fallen on the road"
python code/graph/runtime.py --selftest
```

`--turn` prints the resulting state as JSON and writes no row. `--selftest` runs the tree, greeting, silence, emergency and duplicate turns on a temporary database and prints one line per turn.

---

## Trajectory scaffold

`code/test_trajectories.py` gains a graph runner:

- `run_graph_case(case)` drives `TurnRuntime.turn` for each turn on a temporary thread.
- The `tree_capture` case asserts the shell produced a captured draft with the resident's words, so the graph is no longer untested.
- The other `layer: graph` cases are reported as `pending` with the step that will implement them, not silently skipped. A pending case must still be loaded and named.
- No fixture expectation changes in this step. Step 10 flips the full expectations and adds the four safety cases.

---

## Tests

`code/test_graph_runtime.py`, `unittest`, offline, `MemorySaver`, temporary thread store.

- a new sender hydrates a new thread with one recent message;
- a second turn hydrates the same thread and appends, capped at 12;
- a repeated `turn_id` is suppressed and does not append twice;
- empty input is suppressed;
- an emergency sets `emergency` and `short_circuit`, calls no model, and does not write;
- a greeting and a "thanks" set the cheap edges; silence suppresses;
- capture produces a draft with the resident's words, `capture_state="captured"`, `routing_status="needs_review"`, `category_id=None`;
- a photo reference is stored as an attachment reference, not bytes;
- the graph compiles with `MemorySaver` and a second invocation resumes the same thread;
- `--selftest` returns one result per scripted turn;
- `test_trajectories.py` runs the tree case through the shell and reports the other graph cases as pending;
- the full suite stays green and no channel module is imported.

---

## Verification

```bash
python code/graph/runtime.py --turn "there is a tree fallen on the road"
python code/graph/runtime.py --selftest
python code/test_graph_runtime.py
cd code && python -m unittest discover -p "test_*.py"
python code/eval/messages.py
git status --short
```

Acceptance:

- `--turn` prints a captured draft; `SELECT COUNT(*) FROM reports` is unchanged.
- `--selftest` reports tree, greeting, silence, emergency and duplicate.
- The full suite is 621 plus the new tests, 4 skips, all green.
- `python code/eval/messages.py` stays 31/31.
- No channel file is changed.
- D53 is in `DECISIONS.md`.
- One commit: `Add the graph shell`.

---

## Goal contribution

| Goal | What Step 6 contributes |
|---|---|
| Natural texting | Neutral. No reply is composed in this step; the writer is Step 9. |
| Actually finish tasks | Serves the first half: the graph owns the turn and the state, and later steps extend the same graph rather than replacing it. |
| One central orchestrator | Serves it structurally: one compiled `StateGraph`, one runtime, one thread key. |
| Useful specialists | Neutral. The playbooks are injected but not called until Step 12. |
| Conversation memory | Serves it: the thread is loaded, appended and checkpointed by `reporter_ref`. |
| Messy input | Serves the capture half: text, photo references and empty input are handled before any classification. |
| No classification trap | Serves it: capture happens before a category is chosen, and no row is written from a wrong label. |
| Ask less | Neutral. The questions start at Step 7. |
| Recover naturally | Neutral. Correction state is Step 10. |
| Concrete action | Neutral. The action decision is Step 7; the write is Step 8. |
| Truthful and safe | Serves the safety precheck, zero model calls on an emergency, and no false row. |
| Usable outcomes | Neutral. The write and the dashboard are Steps 8 and 9. |
| Prove it works | Starts it: the graph runner exists and the tree case runs through the graph. |
| Repo evidence | Reuses the thread store, the playbook index and the safety words rather than inventing new ones. |
| Future phase | Neutral. No new submission or personal-data surface. |

---

## What this step does not do

- No decision model. Step 7 adds `decide`, `validate` and `repair`.
- No write. Step 8 adds the single `reports_db` path.
- No writer, bubbles or outbox. Step 9.
- No corrections, status answer or restart recovery test. Step 10.
- No channel change. Step 11.
- No specialist. Step 12.
- No resident-page truth fix. Step 10 carries D55.

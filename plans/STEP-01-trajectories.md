# Step 1: trajectory fixtures

Scope: one step, one commit. This step creates test data and a loader. It changes no production code and does not start the graph.

Parent plan: `plans/BUILD-STEPS.md`, Step 1. Architecture: `plans/IMPLEMENTATION_PLAN.md`.
Baseline: `40b2ee5`, 475 tests, 31/31 message evaluation.

---

## Context

The graph must be judged against conversations, not single messages. Today the only multi-turn expectations live inside individual tests, so there is no shared artefact that says what the tree conversation should produce, what a correction must do, or how a restart must behave.

This step writes that artefact first, as data. It also records which cases the legacy path already fails, so the graph has a starting score instead of an opinion.

No production file changes. The only new files are a JSON fixture set and its test.

---

## Approach

1. Define eight cases in `code/eval/trajectories/cases.json`.
2. Write `code/test_trajectories.py` with two jobs:
   - validate every fixture's shape,
   - run the agent-layer cases against the current `TriageAgent` with a scripted model, and assert the recorded legacy status.
3. Mark the graph-only and channel-layer cases as not runnable in this step. They are loaded and validated, then skipped with a reason. They become runnable at Step 6 and Step 11.
4. Do not assert the desired graph behaviour yet. The `expect` block is the target; the legacy assertion is the baseline.

The suite stays green. A documented legacy failure is asserted as a failure, not left red.

---

## Files

New, and only these:

```text
code/eval/trajectories/cases.json
code/test_trajectories.py
```

Not touched: everything under `code/`, `agent/`, `dashboard/`, `plans/`.

---

## Reuse

| Need | Use |
|---|---|
| Temp DB and stubs | the pattern in `code/test_agents.py` `AgentCase.setUp` |
| Turn entry | `agents.ORCHESTRATOR.handle`, `agents.Turn` |
| Scripted model | `triage.llm.chat` patched, as in `test_agents` |
| Reply capture | `ORCHESTRATOR.set_notifier` |
| Model decision shape | `code/test_agents.py:model()` |
| Row assertions | `reports_db.connect`, `SELECT ... FROM reports` |

Do not import `test_agents` from the new test. Copy the fixture pattern. A test module importing another test module makes discovery order load-bearing.

---

## Fixture schema

```json
{
  "name": "tree_capture",
  "layer": "agent",
  "legacy": "pass",
  "turns": [
    {"text": "there is a tree fallen on the road",
     "model": {"is_report": true, "category_id": "flooding_severe_weather",
               "location": "", "description": "tree fallen on the road",
               "severity": null, "confidence": 0.9}}
  ],
  "expect": {
    "rows": 1,
    "categories": ["unclear_other"],
    "locations": ["Not given"],
    "reply_contains": ["hasn't gone to the council"],
    "reply_forbids": ["The council has it", "crew"],
    "max_questions": 1
  }
}
```

Rules:

- `layer` is `agent`, `graph` or `channel`.
- `legacy` is `pass`, `fail` or `not_applicable`.
- `turns[].model` is the exact triage decision the scripted model returns.
- `expect` describes the desired graph behaviour. It is validated for shape now, consumed from Step 6.
- No fixture may assert a fact that is not in `agent/confirmed_with_websites.csv`.

---

## The eight cases

| # | Name | Layer | Legacy today | What it must prove |
|---|---|---|---|---|
| 1 | tree_capture | agent | pass | An info-only category on a real report still saves one row and claims nothing |
| 2 | challenge_retraction | agent | fail | The second turn retracts the flooding reading, keeps the row, asks once |
| 3 | wrong_specialist | graph | fail | A mismatch preserves the draft and reroutes once |
| 4 | null_patch | graph | fail | A null-filled patch cannot clear a known location |
| 5 | photo_after_text | agent | pass | A late photo attaches to the open report, no second row |
| 6 | two_incidents | agent | fail | Switching to a second problem creates a second row and does not overwrite the first |
| 7 | duplicate_webhook | channel | not_applicable | The same message guid twice makes one row and one reply |
| 8 | restart | graph | fail | A new runtime instance resumes the pending question and keeps one row |

`legacy: pass` means the current `TriageAgent` already satisfies the case at its layer. `fail` means it does not, and the test asserts that gap. `not_applicable` means the layer does not exist yet.

---

## Test file behaviour

`code/test_trajectories.py`, `unittest`, offline.

`FixtureTest`:

- loads the file, asserts exactly 8 cases;
- asserts unique names;
- asserts every required key and the allowed enum values;
- asserts each case has at least one turn and an `expect` block;
- asserts every `reply_forbids` string is not also in `reply_contains`.

`LegacyStatusTest`:

- for `layer: agent`, runs the case on a temp database with the same stubs as `test_agents.AgentCase`, captures rows and replies, and asserts `legacy`:
  - `pass` means the stated expectations for rows, categories and locations hold today;
  - `fail` means at least one stated expectation does not hold.
- for `graph` and `channel`, skips with a clear reason. It does not pretend to run.

The test prints one line per case: name, layer, legacy status, and the first unmet expectation.

Expected output at this step: 8 fixture checks pass, 4 legacy checks pass, 4 skips with reasons.

---

## What this step deliberately does not do

- It does not create `code/graph/`.
- It does not change `triage.py`, `tools.py`, `messages.py` or the channel.
- It does not fix the challenge path. It records that the challenge path currently returns the generic council link and no retraction.
- It does not assert the desired graph outcome as a passing test. That comes when the graph runner exists.

---

## Verification

```bash
python code/test_trajectories.py
cd code && python -m unittest discover -p "test_*.py"
python code/eval/messages.py
git status --short
```

Acceptance:

- `python code/test_trajectories.py` passes and reports 8 fixtures, 4 legacy checks, 4 skips.
- The challenge case demonstrates the current failure: one row, no retraction, the generic link repeated.
- The full suite remains at 475 plus the new tests, all green.
- `git diff --name-only` for the step lists only `code/eval/trajectories/cases.json` and `code/test_trajectories.py`.
- One commit: `Add trajectory fixtures for the reported failures`.

---

## Risks

- Asserting a legacy failure can look like blessing it. The fixture says `legacy: fail` and the test asserts the failure; Step 10 flips the same case to the graph and requires `expect` to pass.
- The scripted model must match what the real model returned in the reported case. The decision above is the one from the reproduction, with `is_report: true` and `flooding_severe_weather`.
- Row counts use `init_db(seed=False)` so 68 synthetic rows do not pollute the expectation.

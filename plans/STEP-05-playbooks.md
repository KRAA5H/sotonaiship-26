# Step 5: verified playbooks

Status: approved, audited, implemented. The Step 5 goal audit blocked the first design; its fixes are in the files and in this record.

Scope: one step, one commit. Data generation only. No graph, no policy change, no model, no network.

Parent plan: `plans/BUILD-STEPS.md`, Step 5. Architecture: `plans/IMPLEMENTATION_PLAN.md`, sections 6 and 7.

---

## Context

Step 4's policy is only as good as the data it is given: which categories exist, which outcome each has, which three are handoffs, which are never saved, which facts have a checked date, which questions a service may ask, and which numbers and teams are allowed.

That data is split across `agent/categories.json` (22 categories), `agent/confirmed_with_websites.csv` (54 dated rows) and `agent/loader.py` (the join). Hand-writing playbooks would create a second source of truth. The playbooks are generated, and `--check` fails if any category, fact, date or outcome drifts.

---

## Audit fixes applied

The Step 5 goal audit found the first design would have made five categories permanently non-actionable and would have left Step 6 reaching back into `categories.json`.

- `required_local` now uses the draft's vocabulary only: `description`, `location`, `address`. The rulebook fields that the draft cannot hold (`road_name`, `which_bin`, `time_observed`, `vehicle_registration_if_visible`) are kept in `required_detail` for the specialist and the officer view.
- `required_capture_any` is `["description", "photo"]` for savable categories. A photo-only iMessage is the most likely messy input, and it now captures. Non-savable categories (`info_only`, `not_council`, the three handoffs) carry `save: false`, empty `required_local` and empty `required_capture_any`, so a consumer cannot mistake them for actionable.
- The version travels on `SpecialistResult` and on `ExecutedOutcome.playbook_version`, so a deterministic save records the playbook that produced it.
- `required_submission` stays empty, with `submission_status: "unverified"`. An empty list must never be read as "satisfied".
- The index carries the fields Step 6 and Step 12 would otherwise re-read: `groups`, `teams`, `numbers`, `guidance`, `guidance_by_category`, `allowed_questions_by_category`, `location_modes`, `duplicate_windows`, `fact_ids` and `general_fact_ids`.
- `specialist_group` is one of the four specialist groups; `rulebook_group` keeps the finer label. Pothole is `highways` for the specialist and `roads_and_parking` in the rulebook.
- The nine `general`-only fact rows are in `general_fact_ids`, and `known_facts` covers all 54 rows. The adult social care number and the council scope facts remain quotable.
- Each fact carries `fact_key`, a content hash, so a positional `F0xx` id changing after an insertion is detectable.
- `info_student_waste_rules` falls back to `answer_source` when `source_url` is absent.
- `duplicate_window_days` falls back to `meta.duplicate_rule.default.window_days` (30) for the nine categories without an `agent` block.
- JSON, not YAML: no YAML parser is installed, and `--check` needs an exact byte compare. `BUILD-STEPS.md` and `IMPLEMENTATION_PLAN.md` are amended in the same commit.

A second goal audit checked the generated files. Its fixes:

- `ExecutedOutcome.playbook_version` carries the version on the ordinary save, not only on `SpecialistResult`.
- Non-savable categories carry `save: false` and no actionability, so a consumer cannot mistake `not_council_utility` for a report.
- `forbidden_team_names` is curated; the organisation name and process labels are safe to say.
- Questions carry `send_ready: false`; they are intent, not SMS copy.
- `source_status` and `guidance_checked` mark inherited sources honestly. The trunk-road source is unverified and must not be cited until `agent/` carries a checked page.

---

## Files

```text
code/services/__init__.py
code/services/build_playbooks.py
code/services/playbooks/_index.json
code/services/playbooks/<category_id>.json     one per category, 22
code/test_playbooks.py
plans/STEP-05-playbooks.md
```

Not touched: `agent/`, `code/graph/`, `code/agents/`, `code/tools.py`, `dashboard/`.

---

## Playbook content

One file per category. Fields are copied or derived, never invented.

```json
{
  "id": "pothole",
  "service_id": "pothole",
  "version": "0.3+<first 12 of sha256(csv)>",
  "source_date": "2026-10-17",
  "generated_from": {"categories": "0.3", "facts_date": "2026-10-17"},
  "label": "Pothole",
  "rulebook_group": "roads_and_parking",
  "specialist_group": "highways",
  "outcome": "council_report",
  "location_mode": "pin",
  "handoff": false,
  "save": true,
  "emergency": false,
  "team": "Highways",
  "team_confirmed": false,
  "duplicate_window_days": 30,
  "required_capture_any": ["description", "photo"],
  "required_local": ["description", "location"],
  "required_detail": ["road_name"],
  "rulebook_required_fields": ["location", "description", "road_name", "photo_recommended"],
  "required_submission": [],
  "submission_status": "unverified",
  "questions": [
    {"field": "location", "text": "Which road, and nearest house number or junction?", "send_ready": false},
    {"field": "detail", "text": "Roughly how big and how deep?", "send_ready": false}
  ],
  "allowed_question_fields": ["description", "detail", "location", "photo"],
  "form_url": "https://...",
  "source_url": "https://...",
  "source_status": "checked",
  "form_notes": "...",
  "severity": {"high": ["..."], "low": ["..."]},
  "severity_keywords": {"high": ["..."], "low": ["..."]},
  "detail_question": "Is it in the road, a cycle lane or on the pavement?",
  "detail_words": ["road", "pavement", "cycle"],
  "detail_pattern": null,
  "redirect_to": null,
  "show_guidance": [],
  "info_first": false,
  "check_ownership": "If the road is a motorway, or a named trunk or main road...",
  "note": null,
  "example_phrases": ["..."],
  "fms_categories": ["..."],
  "facts": [
    {"id": "F012", "fact_key": "a1b2c3d4e5f6", "topic": "...", "fact": "...",
     "url": "https://...", "date": "2026-10-17", "caveat": "..."}
  ]
}
```

Rules:

- `required_capture_any` is an any-of list for savable categories. `description` or `photo` is enough to capture.
- `save` is true only for a `council_report` category that is not a handoff. The three handoffs and all `info_only`/`not_council` categories have `save: false`, no local requirements and no capture requirement.
- `required_local` is `["description", "location"]` for pin mode and `["description", "address"]` for address mode. It decides `locally_actionable`, not capture. Every entry is a field the draft can hold.
- `required_detail` is the rulebook's extra fields, for the specialist and the officer view. It never blocks capture or actionability on its own.
- `required_submission` is `[]` and `submission_status` is `"unverified"` for every category. A consumer must require a non-empty, satisfied list before `submission_ready`.
- `handoff` is true exactly when `location_mode == "handoff"`: `noise_nuisance`, `other_nuisance`, `property_concern`. The rulebook still calls them `council_report`; the index separates them so the policy and the playbook cannot disagree.
- `questions` copies `follow_up_questions` verbatim. The first question is `location` for pin mode, `address` for address mode; the rest are `detail`, because the rulebook does not attach a field name to a prose question. `required_detail` carries the real extra fields.
- `allowed_question_fields` is per category, and the index also exposes the union.
- `facts` are the CSV rows whose `category_id` contains the id, in CSV order. `id` is positional `F001` to `F054`; `fact_key` is a content hash so an insertion is detectable.
- `team` is carried but never spoken: `team_confirmed` is false on all 22. The index's `forbidden_team_names` is the curated set of unconfirmed team labels, excluding the organisation name and process labels that are safe to say.
- `source_url` falls back to `answer_source` for the one info category that has no `source_url`. `source_status` is `checked` only when the URL appears in the fact sheet, `unverified` when it is inherited but not checked, and `none` when absent. The trunk-road source is currently `unverified`; it must not be cited until `agent/` carries a verified National Highways or council page.
- `questions[].send_ready` is false. The rulebook prose is intent, not SMS copy; the writer composes the sentence.

---

## The index

`code/services/playbooks/_index.json` is the single object Step 6 injects.

```json
{
  "version": "0.3+<hash>",
  "generated_from": {"categories": "0.3", "facts_date": "2026-10-17",
                     "fact_count": 54, "category_count": 22},
  "categories": {"pothole": "council_report", "...": "..."},
  "handoff_categories": ["noise_nuisance", "other_nuisance", "property_concern"],
  "never_saved": ["outside_southampton", "not_council_trunk_road", "not_council_utility"],
  "emergency_categories": ["..."],
  "groups": {"cleansing": ["dog_fouling", "..."], "highways": ["..."],
             "waste": ["..."], "housing": ["..."]},
  "savable_categories": ["...13 ids..."],
  "teams": ["..."],
  "forbidden_team_names": ["...unconfirmed labels..."],
  "numbers": ["023 8023 3344", "0300 555 1373", "0300 123 5000", "..."],
  "guidance": {"emergency": {"contact": "999"}, "council_out_of_hours": {"..."}},
  "guidance_checked": ["council_out_of_hours"],
  "guidance_by_category": {"flooding_severe_weather": {"show_guidance": ["emergency"]}},
  "allowed_questions": ["address", "description", "detail", "location", "photo"],
  "allowed_questions_by_category": {"pothole": ["description", "detail", "location", "photo"]},
  "location_modes": {"pothole": "pin", "missed_bin": "address"},
  "duplicate_windows": {"pothole": 30, "missed_bin": 7},
  "known_facts": {"https://...": "2026-10-17"},
  "fact_ids": {"F001": {"url": "...", "date": "2026-10-17", "fact_key": "...", "categories": []}},
  "general_fact_ids": ["F002", "F..."],
  "playbooks": {"pothole": "pothole.json"}
}
```

- `categories` and `never_saved` come from the rulebook outcomes.
- `handoff_categories` comes from `location_mode == "handoff"`.
- `known_facts` is URL to `date_checked` for all 54 rows, including `general`.
- `numbers` is the guidance contacts plus every phone-shaped number in the fact text. It feeds the policy's `allowed_numbers`.
- `teams` is every non-null team name. `forbidden_team_names` is the curated subset that may never be spoken, excluding `Southampton City Council` and `Manual review`.
- `groups` maps the four specialist groups to category ids; categories with no specialist group are absent.
- `duplicate_windows` and `location_modes` let Step 6 avoid opening 22 files per turn.

---

## Generator

```bash
python code/services/build_playbooks.py            # write the files
python code/services/build_playbooks.py --check    # exit 0 if identical, 1 with the drift
```

- Reads `agent/categories.json` and `agent/confirmed_with_websites.csv` directly.
- Splits `category_id` on `;` and strips, matching `agent/loader.py`.
- Writes sorted, indented JSON with a trailing newline.
- `--check` regenerates in memory and compares bytes. It never writes.
- No network, no model, no clock.

---

## Tests

`code/test_playbooks.py`, 25 tests, offline.

- 22 playbooks plus `_index.json`; no extras.
- `--check` exits 0; two builds are identical; a mutated file is `stale`, an extra file is `extra`.
- Source files are unchanged by a build.
- Every `required_local` entry is `description`, `location` or `address`.
- Every `required_capture_any` for a savable category contains description and photo; non-savable playbooks carry neither.
- Exactly 13 categories are savable; the handoffs and the six info/not-council categories are not.
- Questions are marked `send_ready: false`.
- `forbidden_team_names` excludes the organisation and process labels.
- `source_status` marks the trunk-road source unverified; `guidance_checked` lists only the dated guidance.
- `required_submission` is empty and `submission_status` is unverified everywhere.
- `team_confirmed` is false everywhere.
- `specialist_group` is one of the four or null; the groups index covers 12 categories.
- `unclear_other` has no facts and is neither handoff nor never-saved.
- `required_detail` keeps `road_name`, `which_bin` and `vehicle_registration_if_visible`.
- `source_url` falls back to `answer_source`.
- Duplicate windows fall back to 30; missed bin is 7.
- Every non-general fact row appears in a playbook; the nine general rows are in `general_fact_ids`.
- `known_facts` covers every URL; no fact is invented.
- Fact ids are contiguous, keys are unique, and a shared row keeps one id.
- Numbers include the out-of-hours, adult social care and National Highways numbers; teams are present.
- Guidance includes emergency and out-of-hours; the trunk-road and flooding categories carry their guidance.
- Two dates for one URL raise.

---

## Goal contribution

| Product goal | What Step 5 contributes |
|---|---|
| Natural texting | Neutral. `questions` are intent, not send-ready copy; the writer owns the words. |
| Actually finish tasks | `required_local` and `required_detail` tell the graph exactly what is missing, so it can finish. |
| One central orchestrator | Neutral data; the index is what the graph injects. |
| Useful specialist subagents | `specialist_group`, `detail_question`, `detail_words`, `detail_pattern` and the facts give a specialist something to reason with. |
| Conversation memory | The version travels on `SpecialistResult` and the executed outcome; the draft is not claimed to hold it. |
| Handle messy input | `required_capture_any` includes photo; `required_local` separates capture from actionability. |
| No classification trap | `unclear_other` has a playbook and no facts; every category has a file. |
| Ask less | One question per missing field, worded by the rulebook; per-category allowed fields stop an invented question. |
| Recover naturally | Neutral. The policy and writer own retraction; the version makes a stale fact visible. |
| Take a concrete action | `required_local` and `required_submission` feed log, ask, answer and escalate. |
| Truthful and safe | Every fact has a URL and checked date; `team_confirmed` is false; `required_submission` is empty and marked unverified; numbers and teams are allowlisted. |
| Usable outcomes | Duplicate windows, location modes, required fields and detail fields make a report officer-ready. |
| Prove it works | `--check`, the byte-identical build and 21 data tests prove the graph reads the same data the team verified. |
| Use repo evidence | Generated from `agent/`; the field renames and JSON choice are recorded in the parent plans. |
| Future phase | `form_url` and `form_notes` are retained as data; nothing is submitted and `submission_status` stays unverified. |

---

## Verification

```bash
python code/services/build_playbooks.py --check
python code/test_playbooks.py
python code/test_graph_policy.py
cd code && python -m unittest discover -p "test_*.py"
python code/eval/messages.py
git status --short
```

Acceptance:

- `--check` exits 0.
- 21 playbook tests and 62 policy tests pass.
- The full suite is **625 tests, 4 skips**, all green.
- `python code/eval/messages.py` stays 31/31.
- The changed files are `code/services/`, `code/test_playbooks.py`, this plan, and the JSON notes in `BUILD-STEPS.md` and `IMPLEMENTATION_PLAN.md`.
- One commit: `Generate verified playbooks`.

---

## What this step does not do

- No specialists. Step 12 uses the highways playbook; Step 6 injects the index.
- No prompts. The decide prompt in Step 7 reads the playbook, but the prompt is not generated here.
- No submission requirements. `required_submission` stays empty and `submission_status` unverified until a form is checked field by field.
- No category list change. The 22 come from the rulebook; a tree category needs a confirmed fact row first.
- No natural-language copy. The writer in Step 9 owns every resident-facing word.

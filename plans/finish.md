# Kerbside: finishing the product

**Phase 1 is now RAG and resident messages: see `plans/rag-and-messages.md`. Everything below is phase 2, done after phase 1.**

Plan mode. Nothing built yet.

## Context

v1 works end to end: text or photo, triage, report row, council card, resident link, status change. 106 tests, verified on a real iMessage. That is the spine.

What is missing is the product around the spine: the numbers that prove the AI works, the officer's reason to open it, the work order the pitch promises, the text that closes the loop, and answers that cite a source instead of sounding confident.

Deferred by decision, not forgotten: predictive pane, 80 metre distance dedupe (no coordinates in the schema), SMS and simulator, tiered ownership. Video, README and the public repo belong to the end of the hackathon and are not in this plan.

Privacy decision taken: the resident's handle is stored in a separate `contacts` table so the council can text them when a job is done. `reporter_ref` stays a one-way hash for analytics.

## Approach

Six pieces, in dependency order. Each ends with tests and a live check, and nothing is counted as done until the demo path still passes.

### 1. Priority with visible factors

`code/priority.py`, pure functions, no schema change. Score computed on read so no migration and no backfill.

- severity: high 3, medium 2, low 1, not set counts as medium.
- exposure: from the category's group, traffic-facing 3 down to cosmetic 1.
- cluster: other open reports at the same place, as `check_duplicate` already counts them.
- age: days open, capped.

`score = severity x exposure x (1 + 0.25 x (cluster - 1)) + min(age_days / 7, 3)`, and the card shows the four factors, not just the number. A score nobody can explain is a black box.

### 2. Contacts and work orders

Two tables, added to `dashboard/schema.sql` with `IF NOT EXISTS` on all three, and `init_db` runs the file on every start so existing databases gain them.

- `contacts(report_id PRIMARY KEY, chat_guid, created_at, last_notified_status, last_notified_at)`.
- `work_orders(id PRIMARY KEY, report_id UNIQUE, team, crew, scheduled_for, status, created_at)`.

`code/reports_db.py` gets `remember_contact`, `work_order_for`, `create_work_order`, `tomorrow_jobs`. `blue_bubbles` calls them after a successful save, so `tools.py` keeps its current signature.

### 3. Mock works chain

`code/works.py`. On intake, a council report gets one work order for the rulebook's `team`, scheduled the next weekday at 08:00, id `WO-0001` upward. Labelled "Mock works system, Confirm not connected" wherever it appears.

- `/council/tomorrow`: jobs for the next weekday, grouped by team, sorted by priority, each row showing the report, street, severity and factor breakdown.
- `/council/tomorrow.csv`: same list, exportable.
- Nav link from `/council`.

### 4. Completion text

`code/notify.py`. The status route gains one hook: when a report moves to `resolved`, look up the contact, send one short text through `bb.send_text`, and record `last_notified_status`.

- Never blocks the status change. A send failure is logged, the database keeps the new status, the officer sees a warning.
- One text per transition, not per click.
- Copy names the report type and street and links to `/r/<token>`, and says to reply if it is not fixed. That reply arrives as a normal inbound message.

### 5. RAG grounding with real citations

`code/rag.py`, retrieval over the 53 dated facts in `agent/confirmed_with_websites.csv` through `agent/loader.py`.

- `retrieve(question, category_id, k=3)`: category match plus token overlap, stopwords removed. No embeddings: DeepSeek exposes no embedding model, and a keyword scorer over 53 facts is honest and debuggable.
- `answer(...)`: the model writes the body only. We append "Source: name, checked date, url" from the retrieved row, so provenance is never model-generated.
- Wired in when triage says not a report and the message is a question. Falls back to today's canned guidance if retrieval finds nothing.
- Tests with a fake model: retrieval ranks the right fact, a fact-free question gets "I do not know" plus the official link, and every citation matches a retrieved row.

### 6. Evaluation and `NUMBERS.md`

`code/eval/`. Real data, cached, with a date.

- Fetch the Southampton listing pages (verified: 200 report links per page) plus the report pages for descriptions, one request per second, raw bytes cached in `code/eval/raw/`. Open311 is throttled to 503 right now, so it is a secondary source only.
- 60 reports labelled into our 22 categories with a written tie-break rule: 15 pothole, 15 dumped rubbish, 15 street furniture and lighting, 15 deliberately ambiguous or multi-issue. I label, you spot-check fifteen, and `NUMBERS.md` states exactly that rather than claiming two independent labellers.
- Keyword baseline in `code/eval/baseline.py`, same 60, same scoring.
- Model run through `triage.triage` with no database writes; `llm.chat` gains an opt-in usage return so cost per report is measured, not guessed.
- Duplicates: real same-street pairs from the fetched data plus 20 hard negatives (same street different category, adjacent streets same category), run through `check_duplicate` on a temp database. Report catch rate and false positives, losses included.
- `NUMBERS.md`: one table, model versus baseline, duplicate rates, interactions to report, measured cost per report, officer minutes as a stated assumption, method, sample size, fetch date, sources.

### 7. Safety and edges

- Emergency guard in `triage.py` before the model: gas, fire, trapped, live wire, injury returns `reason="emergency"`, and the reply is "Call 999 now", then logs if it is safe. Deterministic, testable without a network.
- Server-level tests for the four refusal outcomes, a model timeout that falls back to the stub, and two concurrent saves.

## Files

- New: `code/priority.py`, `code/works.py`, `code/notify.py`, `code/rag.py`, `code/test_priority.py`, `code/test_works.py`, `code/test_rag.py`, `code/eval/fetch.py`, `code/eval/baseline.py`, `code/eval/run.py`, `code/eval/labels.csv`, `NUMBERS.md`
- Changed: `dashboard/schema.sql`, `code/reports_db.py`, `code/blue_bubbles.py`, `code/triage.py`, `code/llm.py` (usage), `code/website.py`, `code/web/templates/council.html`, `code/test_tools.py`, `code/test_bot.py`
- Untouched: `code/bb.py`, `code/tools.py` signatures, `agent/categories.json`, `agent/confirmed_with_websites.csv`

## Reuse

- `reports_db.connect` already sets WAL and a busy timeout, so concurrency work is only a test.
- `tools.check_duplicate` and its `_same_place` matching feed both the priority cluster factor and the duplicate evaluation.
- `agent/loader.load` already joins the category rules to the dated facts.
- `website._connect` and `website.set_status` are the hook points for notification.
- `test_tools.DbCase` gives each test a fresh seeded database, so new table tests extend it rather than inventing a harness.

## Steps

- [ ] Priority module and card column, with factor breakdown
- [ ] Schema additions, contacts and work order helpers, migration on start
- [ ] Work order created at intake, tomorrow list and CSV
- [ ] Completion text on resolve, idempotent, failure-safe
- [ ] RAG retrieval and grounded answers, wired to info questions
- [ ] Emergency guard and server-level edge tests
- [ ] Eval fetch and cache, 60 labels, user spot-check
- [ ] Baseline, model run, usage capture
- [ ] Duplicate pairs and hard negatives
- [ ] `NUMBERS.md`, then the demo run three times

## Verification

| Check | Expected |
|---|---|
| A pothole text | card shows priority plus four factors, work order `WO-0001` for tomorrow 08:00 |
| `/council/tomorrow` | job grouped under its team, sorted by priority, CSV matches the page |
| Officer presses Resolved | exactly one text, link shows resolved, second click sends nothing |
| "how long do potholes take to fix" | answer from a dated fact with source name, date and URL |
| "what is the meaning of life" | no invented answer, official link instead |
| "smell of gas outside" | 999 reply, no row saved |
| `python code/eval/run.py` | model versus baseline table, cost per report, losses included |
| All suites | existing 106 tests still pass, plus the new ones |
| Demo, three runs | no manual step, no dead end, every number on screen sourced |

## Order and time

Tonight 20:00 to 00:00: pieces 1 to 4, plus the emergency guard. After midnight: eval fetch and labelling in parallel subagents while RAG is built. 02:00 to 03:00: the numbers. Then rehearse the demo three times before anyone sleeps.

Two defaults I chose, say if you want otherwise: work orders are created automatically at intake rather than by an officer clicking Dispatch, and the tomorrow list is its own page rather than a tab on the dashboard.

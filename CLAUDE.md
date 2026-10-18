# Project context for Claude (SotonShip 2026, Southampton City track)

## What we are building
An AI assistant residents message on iMessage (demo runs from one team Mac) to report council issues or ask questions.
- Info questions: answer only from verified facts in agent/confirmed_with_websites.csv, with source link and date.
- Council issues: ask follow-up questions (max 5 exchanges), save one structured report, check for duplicates, then send the resident a private link.
- Not council / outside Southampton / emergency: point to official guidance (999, National Highways, utilities), save nothing.
Submissions lock Sunday 18 Oct 2026 13:00.

## Files
- agent/categories.json: rulebook (22 fully confirmed categories, outcomes, follow-up questions, official form links, location rule). Only fully confirmed items are allowed.
- agent/confirmed_with_websites.csv: fact sheet (54 rows, source URL + date 2026-10-17). category_id may hold several ids separated by ";".
- agent/loader.py: joins the two on category_id.
- dashboard/schema.sql + SCHEMA.md: reports table, 11 columns (id, created_at, category_id, status, severity, location, description, has_photo, duplicate_of, reporter_ref, link_token). No coordinates, no channel column.
- dashboard/fake_reports.*: 68 SYNTHETIC reports. dashboard/prototype/index.html: clickable prototype.
- reference/: team/judge material. Do NOT load into the agent.

## Decisions
- Website: one site, two views. /council (staff dashboard, private) and /r/<link_token> (resident sees only their own report). Never put the report id in a public link.
- Database: SQLite file on the demo Mac. Never commit it (.gitignore).
- Agent tools planned: find_category_facts, check_duplicate, save_report (returns link_token), get_report_status. Start as plain tool use in the relay script; wrap as an MCP server only if time allows.
- Duplicate rule: same category, same location text, within 30 days (placeholder).
- Location: ask where the PROBLEM is. Do not judge the city boundary from postcode prefix alone (council says some SO16/SO18/SO19 addresses are outside the city).

## Rules
- Never state anything not in confirmed_with_websites.csv. Show date checked.
- API keys go in .env, never committed.
- In plan mode, delegate only to read-only subagents (scout, reviewer, oracle, evidence-auditor).
  Plannotator's planning write gate only intercepts write/edit in the main session, so a writer
  child (worker, delegate, claude-code-writer) would edit code behind the gate.
- Approved plans execute under .pi/plannotator.json, which sets the delegation policy. Restart
  or /reload for config changes to apply.
- Named trunk or main roads: if a resident reports an issue on a named trunk or main road (A33, A36 or similar) and the facts don't say who is responsible, say once that you can't confirm who looks after that road, point them to the council's roads page (https://www.southampton.gov.uk/travel-transport/report-issue/potholes/) or National Highways, and do not save a report.
- Council out-of-hours emergency number is 023 8023 3344 (confirmed fact, source and date in the fact sheet). Adult social care out of hours is 0300 555 1373.

## Codebase cache (read before exploring)
- `_pi/sotonaiship-26/CODEBASE-MAP.md` in the vault: call chain, module index, exact DB contracts, test seams, drift list. Raw scout reports in `_pi/sotonaiship-26/scouts/`.
- `_pi/sotonaiship-26/IMPLEMENTATION-PLAN-CONTEXT.md`: `plans/IMPLEMENTATION_PLAN.md` against the code, with the conflicts to settle first.
- Corrections to the summary above, verified 2026-10-18: `dashboard/schema.sql` has **16** columns, not 11 (photo_guid, photo_mime, area, status_changed_at, photo_features were added). `agent/categories.json` has 22 categories of which **16 are `council_report`**, and **there is no tree category**. Live turn path is `blue_bubbles.handle_inbound` -> `agents.TriageAgent(handle)`, not `code/triage.py`. 475 tests pass offline: `cd code && python -m unittest discover -p "test_*.py"`.

## D65 profile override (2026-10-18)

The operator overrides the no-PII rule for this pilot. A separate `profiles` table may
store preferred name, address and phone, keyed by the salted reporter reference. Reports,
`/r/<token>` and the public dashboard never carry those fields. The writer may use the
first name and never reads the phone back.

## Open items
- Decided to leave out: A33/A36 responsibility not confirmed.
- Most council multi-step forms only read to their first steps.

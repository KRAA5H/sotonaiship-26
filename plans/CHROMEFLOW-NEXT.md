# Chromeflow next

Status: next step, not implemented. The LLM side is frozen by `LLM-FREEZE.md`; this work uses the existing task and adapter layer and does not change the director, writer, prompts or evidence.

## Why

The dashboard, tasks and evidence already show the workflow. Chromeflow is the fastest way to sell the agentic side visually: the agent drives a real council form in a browser, fills the resident's details, pauses before submission, and captures the proof. The council can later replace Chromeflow with a direct integration, using the same adapter boundary.

## Demo path

1. Resident asks for a parking permit.
2. The director collects name, address and vehicle one field at a time into the existing task.
3. The adapter opens the real Southampton parking permit page with Chromeflow.
4. Chromeflow fills the form and stops at the review or payment screen.
5. The resident or operator confirms. A human submits.
6. The confirmation reference, URL, screenshot and filled fields are stored against the task.
7. The task page and `/council/tasks` show the evidence. The resident gets the reference and an honest status.

No task is marked submitted before the confirmation page exists. No reference is invented. If the form changes or Chromeflow cannot complete it, the task stays prepared and the failure is recorded.

## Implementation shape

- `CouncilAdapter` already has the task and reference shape. Add `ChromeflowAdapter` beside the sandbox adapter.
- Tools: `open_permit_form`, `fill_permit_form`, `capture_form_state`, `confirm_submission`, `record_reference`.
- Store `case_events`: step, URL, screenshot path, fields, result, timestamp, task id.
- The web app shows a `Open the form` or `Review in browser` action on the task page.
- A human confirmation step is mandatory before the submit click.
- The council dashboard reads the same task and events; do not build a second dashboard.

## Guardrails

- Consent before opening or filling a real form.
- No automated submit. The final click is human.
- No real personal data in the public repo or logs.
- No claim of council receipt without a confirmation reference.
- One task per request; idempotent by task id.
- Chromeflow is the demo rail. The direct council integration is the production rail; both use the same adapter.

## What to show the judges

Split screen: the chat, the task page, Chromeflow filling the real form, and `/council/tasks` showing the reference and evidence. The point is that the agent took a real action in a real browser and recorded proof, while the council integration remains the target.

## Frozen boundary

Do not change `code/graph/prompts.py`, `writer.py`, `nodes.py`, `execution.py`, `schemas.py` or `evidence.py` for this. Chromeflow is an adapter and UI concern.

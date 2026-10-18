# Kerbside — LangGraph implementation plan

Status: proposed implementation, not a claim about completed code.
Scope: current street-reporting product. Personal-information collection, permit applications, fine challenges and acting on a resident's behalf are Phase 2; see FUTURE.md.

## Agreed architecture

Use one central decision agent, implemented inside a custom LangGraph graph, with category/domain specialist LLM subagents where they add useful reasoning. Keep playbooks alongside agents: a playbook supplies verified requirements and policy; a specialist interprets evidence, chooses bounded tools and returns a recommendation. Neither replaces the other.

This updates the earlier recommendation against subagents: selective specialists are part of the intended design. Do not mechanically recreate the existing nine-stage pipeline as nine agents. The supplied category list, not an invented replacement, should drive the specialist registry.

LangChain documents a central-agent/subagent pattern and custom LangGraph workflows that mix deterministic and agentic behaviour. [web:354][web:448]

## Product invariants

- Accept text, photos, pins, bursts and corrections without an account.
- Capture plausible physical problems before category selection can reject them.
- Keep four outward actions: log, ask one useful question, answer from checked facts, or escalate.
- A turn may internally update a draft while its outward action is ask.
- No generic contact page as a terminal answer.
- Never claim council receipt when only a local record exists.
- Never invent teams, routing addresses, response times, IDs or deadlines.
- Persist corrections and retain the resident's original evidence.
- Use a hashed reporter reference; avoid raw contact identifiers in checkpoints and traces.
- Be concise, human and channel-native, without pretending to be a human officer.

## Ownership and authority

| Component | Owns | Must not do |
|---|---|---|
| Decision agent | Conversation interpretation, specialist selection, next-action proposal | Execute unrestricted writes or treat category as permission to help |
| Specialist subagent | Domain reasoning, evidence assessment, missing-field recommendations | Refuse capture, send DMs directly, invent official requirements |
| Playbook | Verified facts, form requirements, source evidence, routing configuration | Act as a universal refusal gate |
| Policy validator | Hard invariants, budgets, claim permissions | Rely on another model to enforce simple schema rules |
| Tools | Location lookup, draft upsert, report commit, duplicate retrieval, fact lookup | Accept unvalidated model-supplied destinations or SQL |
| Writer | Natural bubbles from executed outcome | Change the decision or claim uncompleted actions |
| Delivery adapter | Ordered sends and receipts | Invent success when transport fails |

The parent remains the single owner of conversation state and final outward decisions. Specialists return structured proposals; the parent and policy layer decide what becomes canonical.

## Graph structure

```text
inbound event → hydrate persistent thread → explicit-danger precheck
    → understand and provisionally capture report-like content
    → decision agent
        → bounded specialist subgraph, if useful
        → inspect result and revise plan, if necessary
    → deterministic policy validation
        → one repair attempt, otherwise safe capture/human fallback
    → execute approved tools
    → build actual-outcome brief
    → compose 1–3 semantic bubbles → lint → enqueue delivery → END
```

On a specialist disagreement, preserve the incident and permit one alternate specialist or a human handoff. A specialist failure never erases the draft. Clarifying questions end the current run and persist a pending question; the next incoming event resumes the same conversation thread.

Use LangGraph subgraphs for domain specialists. The framework supports subgraphs inside parent nodes and different checkpoint persistence modes. Prefer per-invocation specialists with explicit context supplied by the parent; keep multi-turn incident memory in the parent by default. [web:322][web:354]

## State and schema contracts

Persistent thread state should include:

```python
thread_id: str
turn_id: str
recent_messages: list
active_incident_id: str | None
incident_draft: dict
pending_question: dict | None
last_claims_sent: list[str]
last_executed_outcome: dict | None
candidate_services: list[str]
selected_specialist: str | None
specialist_results: list[dict]
plan: dict | None
repair_count: int
specialist_call_count: int
delivery_outbox_ids: list[str]
```

Use an application draft table as the source of truth; LangGraph checkpoints represent execution/conversation state. Persist only JSON-serializable data and attachment references, not photo bytes or provider response objects.

TurnPlan should contain:

- dialogue_act: new_report, detail, correction, challenge_previous_claim, question, status, greeting or other.
- action: log, ask, answer or escalate.
- incident_patch with explicit field updates and supporting evidence.
- service_candidates and optional specialist_request.
- exactly one clarification target when action is ask.
- requested checked facts when action is answer.
- escalation destination when action is escalate.
- retracted_claims and concise reason codes.

Define explicit patch semantics: omitted means unchanged; clear means intentionally remove; set means replace. Do not let a null-filled model response accidentally wipe an existing location or photo.

SpecialistResult should contain:

```json
{
  "service_id": "existing_registry_id",
  "fit": "supported | uncertain | mismatch",
  "observations": [],
  "proposed_patch": {},
  "missing_requirements": [],
  "suggested_question": null,
  "recommended_action": "log | ask | answer | escalate",
  "fact_ids": [],
  "source_refs": [],
  "routing_status": "verified | needs_review",
  "reason_codes": []
}
```

Validate enums and schemas in code. Valid JSON is not proof of a correct decision or supported facts.

## Specialist registry

For each existing category or coherent group, record:

- Stable category IDs and recognition examples.
- Specialist implementation, if any.
- Verified playbook version and fact IDs.
- Allowed tools and read/write permissions.
- Required fields for a local actionable record.
- Separately verified requirements for external submission.
- Emergency considerations and human-review triggers.
- Timeout, model-call budget and fallback behaviour.

Use deterministic handling for simple categories. Use LLM specialists where there are meaningful conditional requirements, overlapping responsibility, conflicting evidence or domain-specific reasoning. Illustrative groupings are highways/obstructions, waste/collections and trees/vegetation; map these against the actual list before implementation.

A specialist must have useful domain tools and a structured result, not merely a different system prompt that repeats classification.

## Capture and readiness

Separate these states:

1. Captured: original evidence and a durable draft exist.
2. Locally actionable: enough information for an officer to investigate.
3. Submission-ready: the destination's verified required fields are satisfied.
4. Submitted: a submission attempt has an authoritative acknowledgment.

Do not assume description plus location satisfies every council form. Unknown category or ownership does not prevent capture. Missing verified submission fields can prevent external submission, not erase the incident.

Keep category candidates rather than an irreversible early label. If routing cannot be established, use needs_triage rather than info_only for physical problems.

## Recovering from mistakes

Mandatory regression:

```text
Resident: there is a tree fallen on the road
System: capture tree incident; select tree/highway specialist; ask location.

Resident: what has that got to do with flooding
System: identify challenge to prior claim; retract flooding interpretation;
        preserve tree incident; continue missing-location question.
```

Proposed bubbles after the mistaken response:

```text
you’re right — that’s not flooding. i got that wrong.
where’s the tree? a road and nearest number, or a pin, is enough.
```

The apology corresponds to an actual state correction, not just warmer copy.

## Natural DM output

Generate a BubblePlan from completed tool outcomes, not a proposed plan.

- Usually one or two bubbles, maximum three.
- One purpose per bubble: repair, question, action or tracking.
- Short contractions and natural lower-case phrasing; no forced slang.
- Do not split into tiny messages just to mimic a person.
- No artificial typing delays; ordered delivery matters more.
- Insert verified URLs and references in code.
- Do not write 'logged with the council' for a local-only record.
- Recheck queued messages against the current turn version before sending stale questions.

Example local-only confirmation:

```text
i’ve saved the fallen-tree report here. it hasn’t been sent to the council yet.
<private tracking link>
```

## LangGraph runtime

Build a custom StateGraph rather than an unrestricted general-purpose agent loop. Add conditional edges for specialist delegation, validation, repair, execution and human review.

Compile the parent with a persistent checkpointer. Subgraph persistence requires a parent checkpointer; per-invocation subgraphs are the documented default for independent specialist requests. [web:322]

Retain one run at a time per reporter, webhook deduplication and burst coalescing. Protect shared case updates with versions or transaction checks; checkpointing does not by itself resolve concurrent application writes.

Use interrupt/resume for real human approvals or review, not every ordinary location question. LangGraph interrupts persist execution state and resume through Command with a thread ID and checkpointer. [web:248]

## Tools and side effects

Reuse the existing location, reports, facts, photo and BlueBubbles modules behind validated functions. Keep code/llm.py initially so provider replacement remains isolated.

Recommended operation boundaries:

```text
upsert_incident_draft
resolve_location
get_service_playbook
run_specialist
find_duplicate_candidates
commit_local_report
get_checked_facts
queue_human_review
enqueue_bubbles
```

Use transactional outbox rows and unique operation keys for report writes and delivery intent. A remote send can still have an ambiguous outcome after a timeout; record that state and reconcile where the provider permits it rather than claiming exactly-once delivery.

Set a global turn deadline and model-call budget. Suggested initial limits: one specialist invocation, one alternate only after mismatch, one plan repair, and a separate bounded writer call. Adjust against measured quality and latency.

## Migration checklist

1. Preserve the current tests; add the exact failed tree conversation as a failing trajectory.
2. Add state/schema contracts and a LangGraph runtime shared by simulator and BlueBubbles.
3. Add provisional draft persistence before service routing.
4. Implement the central decision agent and deterministic validator.
5. Register the existing category list and selectively implement specialist subgraphs.
6. Add parent-mediated specialist handback and rerouting.
7. Bind the writer to actual outcomes and ordered outbox delivery.
8. Add human-review routing and restart recovery tests.
9. Run the old and new paths on the same held-out conversations before switching.

Suggested file ownership:

```text
code/graph/state.py
code/graph/schemas.py
code/graph/build.py
code/graph/policy.py
code/graph/runtime.py
code/specialists/registry.py
code/specialists/<domain>.py
code/services/<service>.yaml
code/eval/trajectories/
```

Keep one writer per file while collaborating. Never commit secrets, live resident records, unredacted screenshots or checkpoint databases to the public repo.

## Evaluation and completion gates

Primary metric: completed actionable outcomes per conversation. Report provisional progress separately from final completion so asking a question does not artificially count as a completed report.

Measure classification accuracy, specialist selection, reroute recovery, false refusal, unnecessary questions, correction recovery, duplicate precision/recall, officer edits, supported-claim rate, latency and cost per completed outcome.

Require tests for:

- Tree misclassification and correction recovery.
- Wrong specialist returning mismatch without losing the incident.
- Known location followed by a null-filled patch.
- Photo arriving after text.
- Multiple problems and explicit switching between incidents.
- Duplicate webhook, process restart and ambiguous send failure.
- Unsupported facts, false submission claims and prompt injection in messages/photos.
- Human-review fallback after budget exhaustion.

Acceptance: both channels use the same graph; category cannot block capture; every factual outward claim has approved provenance; specialist failure degrades safely; report and transport status remain truthful.

## Boundary with Phase 2

Do not collect identity documents, pay fees, submit applications or lodge challenges merely to demonstrate agency in Phase 1. Those capabilities belong to FUTURE.md and require explicit authorisation, verified integrations and stronger personal-data controls.

# Kerbside — Future agentic council services

Status: Phase 2 roadmap, not implemented capability.
Companion: IMPLEMENTATION_PLAN.md defines the current reporting rebuild.

## Purpose

Extend Kerbside from reporting street problems to helping residents complete council tasks: checking eligibility, preparing applications, gathering evidence, drafting challenges and, where authorised and technically supported, submitting on the resident's behalf.

This is optional future scope. The present product must remain useful even if no personal-information collection or transactional automation ships.

## Future architecture

Keep the same parent decision agent and LangGraph runtime. Add service-specialist subgraphs with narrow tools and verified playbooks. A specialist can plan several domain actions, observe results and revise its recommendation; the parent owns the resident conversation and consequential-action permissions.

LangChain supports a central agent coordinating specialist subagents, and custom LangGraph workflows can embed that pattern alongside deterministic logic. [web:354][web:448]

Separate two systems:

1. Development-time discovery: inspect official guidance and real forms to build approved service specifications.
2. Runtime assistance: use approved specifications and authorised tools to help an individual resident.

Do not let an unreviewed browser-discovery output silently redefine live application requirements.

## Real-form discovery agent

Proposed tools: Playwright browser interaction, DOM/accessibility extraction, screenshot capture, official-domain fetch, branch inventory and schema comparison.

```text
Seed official service URL
 → discover guidance and actual form entry point
 → inspect rendered controls and validation
 → explore safe conditional branches
 → extract fields and dependencies
 → compare guidance with observed form
 → record gaps and uncertainty
 → human approval
 → publish versioned service specification
```

Explore only pages and actions permitted by the site and deployment authorisation. Respect rate limits and access controls. Do not bypass authentication, CAPTCHA or anti-bot protections. Do not submit fabricated applications, create fake accounts or trigger payment merely to inspect another screen.

Use labelled synthetic test values only in an authorised sandbox. For production exploration, stop before state-changing actions unless explicit permission covers them.

Treat page text, uploaded documents and tool responses as untrusted content: they provide evidence, not authority to change agent permissions or exfiltrate data.

## Evidence-backed service specifications

Each discovered field should include:

```yaml
field_key: stable_internal_name
observed_label: exact_form_label
input_type: text_or_choice_or_upload
required: true_or_false_or_unknown
visible_when: explicit_branch_condition
validation: observed_validation_or_unknown
provenance_type: observed_in_form_or_guidance_or_unverified
source_url: official_source
observed_at: timestamp
snapshot_ref: redacted_evidence_reference
```

At service level record:

- Form and guidance URLs; version and content fingerprint.
- Conditional branches and unexplored screens.
- Required uploads, formats and size restrictions where observed.
- Identity, account and authentication boundaries.
- Declarations and explicit user choices.
- Fees and deadlines with dated authoritative sources.
- Payment and final-submission boundaries.
- Official acknowledgement and reference format, if observed.
- Reviewer approval and next review date.

A field inferred by an LLM remains unverified. A paper form can inform discovery but is not proof that an online form has identical fields. Guidance inspection is not equivalent to complete interactive-form traversal.

## Resident case model

Evolve reports into typed cases without removing the simpler street-report record:

```text
case_id
case_type: report | application | challenge | enquiry
service_spec_id + service_spec_version
resident_goal
facts + source + confidence + confirmation_state
document_refs
missing_requirements
procedural_stage
proposed_actions
consent_and_approval_records
submission_attempts
receipts
retention_and_access_policy
```

Keep distinct statuses:

```text
captured → gathering → prepared → awaiting_approval
 → submitting → acknowledged
```

Also support blocked, needs_human, failed and submission_unknown. Prepared does not mean submitted; submitted does not mean approved; an HTTP success does not by itself establish authoritative receipt.

## Bounded specialist tools

Illustrative tools, only exposed after implementation:

```python
load_service_spec(service_id)
check_property_eligibility(address)
extract_document_fields(document_ref)
verify_required_evidence(case_id)
retrieve_checked_procedure(service_id, stage)
draft_application(case_id)
draft_challenge(case_id)
request_approval(case_id, payload_hash)
submit_approved_case(case_id, approval_id)
record_submission_receipt(case_id, receipt)
```

The model must never assume a tool exists or that an unofficial lookup is authoritative. Tool availability and permission are explicit parts of the run context.

## Journey: resident parking permit

Southampton states that permit applications may require proof of residence and vehicle ownership, with requirements varying by permit type. Its guidance lists accepted evidence documents. [web:422]

Illustrative flow:

```text
Resident: can i get a parking permit?
Agent: what address would the permit be for?

[Check through an implemented authoritative lookup, or explain the limitation.]

Agent: is the car registered in your name at that address?
Resident: no, it’s my dad’s

[Specialist selects the appropriate evidence branch from the approved specification.]
```

The exact questions, keeper-authorisation requirements and zone/property rules must be verified against the relevant service before deployment. Do not infer eligibility merely from a postcode or street being inside a zone.

The specialist should gather only needed information, extract candidate values from documents, confirm consequential details, validate the package and prepare a resident-readable review. Submission and payment require separate permissions.

## Journey: parking-fine challenge

Southampton's challenge guidance lists a PCN number, contravention code and supporting evidence; it distinguishes the council's challenge process from later procedural steps. [web:434]

Illustrative flow:

```text
Resident: i want to fight this fine
Agent: who issued it? you can send a photo of the notice if that’s easier.

[Extract candidate issuer, notice type, dates and reference.]
[Ask the resident to confirm uncertain or consequential extracted values.]

Agent: what happened when you parked?
```

Specialist workflow:

1. Establish issuer and notice type before selecting a council workflow.
2. Determine procedural stage from the actual notice and checked official guidance.
3. Confirm dates; do not calculate deadlines from uncertain OCR.
4. Gather the resident's factual account and relevant evidence.
5. Draft a challenge that separates facts, supporting documents and requested outcome.
6. Show the complete draft for resident correction and approval.
7. Submit only through an authorised working adapter; otherwise provide the prepared package and concrete assisted next step.
8. Save the acknowledgement and explain exactly what has and has not happened.

Never invent evidence, legal grounds, medical circumstances, procedural rights or success probabilities. Where procedure or deadlines are uncertain, escalate rather than guessing. Southampton warns against false representations and supporting documents. [web:434]

## Journey: conditional service workflows

Other potential specialists include missed collections, housing-service enquiries and permit renewals. Choose new domains based on observed form complexity and available authoritative integrations, not how many agent names can be shown in a diagram.

A good specialist has:

- Meaningful conditional requirements.
- A distinct set of checked knowledge and tools.
- Decisions that change after tool observations.
- A bounded success condition.
- A safe handback when it cannot proceed.

A simple fixed checklist should remain a playbook and deterministic tools.

## Simplification strategy

For every field, choose one treatment:

| Field situation | Treatment |
|---|---|
| Already supplied | Reuse without asking again |
| Available through authorised reliable lookup | Retrieve and record provenance |
| Extracted from a document | Propose, flag uncertainty and confirm when consequential |
| Conditional requirement | Ask only on that branch |
| Truly optional and unnecessary | Skip |
| Declaration or material choice | Ask explicitly |

Optimise the fewest interactions required for a correct complete case, not the fewest questions regardless of accuracy. Never remove official requirements just to improve a demo metric.

## Consent and personal data

A hashed phone number does not anonymise addresses, vehicle registrations, document images or free text. Treat the expanded product as a separate privacy/security design exercise.

Proposed controls:

- Explain why each sensitive item is needed before collection.
- Prefer secure short-lived upload pages over identity documents in ordinary message history.
- Store documents separately with encryption and restricted access.
- Exclude raw document content from routine logs and model traces.
- Define retention, deletion and who can view each case.
- Confirm the legal basis, controller/processor roles and provider data handling before deployment.
- Offer a non-automated route for residents who decline optional automation.
- Do not ask residents to send passwords, payment-card data or one-time authentication codes in chat.

Consent to process a document is not automatically authorisation to submit an application, make a declaration or pay a fee.

## Consequential-action approval

Before submission, show the destination, complete payload, attachments, declarations and any fee. Approval must bind to the exact payload version or hash, not a generic earlier 'yes'.

Any material change invalidates the approval. Use narrowly scoped approval records and server-side checks; the model cannot grant itself permission.

LangGraph interrupt/resume supports pausing a persisted workflow for external approval. It requires a checkpointer, thread ID and resumption command. [web:248]

Payment should be a separate, explicitly authorised flow using an appropriate provider-hosted interface. Do not let a general browser agent handle payment credentials.

## Integration maturity

| Level | Demonstrated capability | Allowed claim |
|---|---|---|
| 0 | Checked guidance | Explains requirements |
| 1 | Form inspection and approved schema | Knows observed fields and branches |
| 2 | Validated prepared package | Prepared, not submitted |
| 3 | Authorised submission attempt | Attempt made; outcome accurately stated |
| 4 | Authoritative acknowledgement | Received by destination |
| 5 | Status integration | Reports verified status changes |

Prefer an official API or agreed integration. Browser automation is an adapter with permissions, fragility and maintenance requirements, not a universal substitute for cooperation with the council.

A blocked form must lead to a useful saved package, assisted handoff or targeted next step, not a false completion claim or unexplained generic link.

## Reliability and change management

- Version service specifications and bind each case to its version.
- Compare form snapshots to detect changes; queue human review before publishing changed requirements.
- Revalidate active cases when a material requirement changes.
- Track field-level extraction uncertainty and document provenance.
- Use bounded tool loops, timeouts and no-progress detection.
- Keep idempotency keys for submission attempts where supported.
- Handle ambiguous timeouts as submission_unknown; reconcile before retrying.
- Keep specialist memory explicit and scoped to the case; no cross-resident leakage.

## Proving real agentic behaviour

Show traces where the same entry point leads to different actions because facts differ:

- Permit applicant is or is not the registered keeper.
- Evidence is complete or a required document is missing.
- Notice is from the council or another issuer.
- Notice is at an initial or later procedural stage.
- A form or lookup contradicts the resident's assumption.
- Resident corrects the draft after extraction.

The proof is an observed plan–tool–result–revision loop leading to a validated outcome, not a hidden chain-of-thought transcript or a large number of agents.

## Evaluation

Compare the original official journey and agent journey using the same task, supplied facts and completion standard.

Measure:

- Correct completed/prepared outcomes, separately from partial progress.
- Required-field completeness and branch-selection accuracy.
- Unsupported requirement, deadline and legal-claim rate.
- Unnecessary questions and resident corrections.
- Accuracy of document extraction after confirmation.
- Valid consent and exact-payload approval coverage.
- Authoritative receipt rate and ambiguous-submission rate.
- Latency, cost and resident effort per completed case.
- Recovery when forms, tools or specialists fail.

Use labelled synthetic resident data in authorised testing. Use real official form evidence without claiming synthetic cases are real applications.

## Staged delivery

1. Discovery only: inspect one permit branch and one PCN-challenge branch; publish evidence-backed specifications.
2. Preparation only: collect the minimum necessary information and produce reviewed application/challenge packages.
3. Approval workflow: add secure uploads, permissions and exact-payload confirmation.
4. Authorised submission pilot: integrate one destination and prove acknowledgement/reconciliation.
5. Status and expansion: add verified updates and further services after measured success.

Do not commit to stages 3–5 for the current submission unless access, authorisation and time genuinely support them.

## Definition of done

A future service is production-ready only when its current requirements are verified, privacy and authorisation controls are approved, failure paths are safe, state survives restart, consequential actions are explicitly authorised, and resident claims match real receipts.

A hackathon demonstration can stop at preparation, provided that boundary is unmistakable.

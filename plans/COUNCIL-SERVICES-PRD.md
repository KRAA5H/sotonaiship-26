# Council services and specialist agents PRD

Status: draft for review. No implementation until the operator approves.

This PRD covers pulling the real Southampton City Council resident-facing problems, services and forms into the repo, and turning them into a small number of specialist agents with eligibility and validation. Chromeflow is explicitly out of scope for this PRD. The LLM side is frozen by `LLM-FREEZE.md`; this work adds a tool and data layer, not new model prompts or schemas unless the operator approves a specific exception.

## Goal

The agent should handle the real council service catalogue, not just the 22 report categories. For every resident-facing report, apply, request or permit service, the repo should hold:

- what the service is and who it is for
- the official page and form URL
- the fields the form asks for
- the documents or details the resident must provide
- the eligibility rules and conditions
- the checked evidence behind every rule and fact
- what the agent can and cannot do without a council integration

A few specialist agents then understand their own service area well enough to ask the right questions, check eligibility, reject an ineligible request honestly, and prepare the correct task or form data. The director still owns the conversation. The writer still owns the human voice. The specialists own the domain rules.

## Scope

In scope:

- all resident-facing report, apply, request, permit, licence, bin, parking, housing, council tax and benefit services discoverable on the public Southampton council site
- the public online forms and their fields
- the official guidance and eligibility pages behind them
- the existing 22 report categories, 54 confirmed facts and 7 imported evidence rows
- source snapshots, dates and change detection
- specialist tools for a few service groups

Out of scope:

- internal council systems, staff back office, committee papers and HR
- automated submission to a council form
- Chromeflow at the moment
- payments and card data
- storing full personal data beyond the D65 profile fields
- inventing a rule, fee, timescale, team or form field that is not on a checked source

The word "all" means all public resident-facing services that have a report, application, request, permit or booking journey. It does not mean every page on the council website.

## Current coverage

The repo currently has:

- 22 categories in `agent/categories.json`
- 54 confirmed facts in `agent/confirmed_with_websites.csv`
- 4 source rows typed as online forms in the fact sheet
- 7 rows in `agent/evidence.csv` for permits, council tax and bins
- playbooks for the existing categories
- a task table with permit fields and a prepared case reference
- no complete service catalogue, no form-field inventory, no rule engine and no specialist agents

## Specialist agents

Keep this small. Four specialists, mapped to the existing specialist groups. Do not add a specialist per category.

### 1. Street scene, group `cleansing`

Covers fly-tipping, litter and street cleaning, dog fouling, dead animals, graffiti and flyposting, broken glass, and other street cleanliness issues. Owns the report form fields, location rules, photo requirements and duplicate rules for these services.

### 2. Highways and parking, group `highways`

Covers potholes and road defects, abandoned vehicles, illegal parking, resident and visitor parking permits, suspensions and parking forms. Owns the eligibility checks for permits, the vehicle and address fields, and the report evidence rules.

### 3. Waste and bins, group `waste`

Covers missed bins, lost or damaged bins, student waste rules, bin sizes, assisted collections and the collection calendar. Owns the bin form fields, the two-working-day rule, contamination rules and the bin-day source boundary. No per-address bin data is claimed unless a verified source exists.

### 4. Housing and money, group `housing`

Covers council housing repairs, council tax discounts and exemptions, and the related application forms. Owns the property, household and income questions that each form actually asks, and the eligibility checks that can be supported by a checked source.

Each specialist returns:

- `service_id` and `specialist` name
- `fit`: supported, uncertain or mismatch
- `observations`: what the resident said and what is missing
- `required_fields`: the fields the form actually requires
- `eligibility`: pass, fail or unknown, with the rule ids and evidence
- `form_url`: the official form or page
- `suggested_question`: exactly one next question
- `evidence`: rows with URL, checked date and quote
- `routing_status`: verified or needs_review
- `reason_codes`

The specialist never speaks to the resident and never writes the reply. It returns structured facts to the director and writer.

## Data model

Add a small, reviewable catalogue. Exact table names can change during implementation; the fields are the contract.

### `council_sources`

- `source_id`
- `url`
- `kind`: page, form, pdf, api
- `fetched_at`
- `content_hash`
- `snapshot_path`
- `http_status`
- `robots_status`
- `review_status`: pending, verified, rejected

### `council_services`

- `service_id`
- `name`
- `group`: cleansing, highways, waste, housing
- `summary`
- `who_it_is_for`
- `page_url`
- `form_url`
- `form_kind`: online, pdf, email, phone, in_person, none
- `source_id`
- `checked_date`
- `status`: verified, needs_review, out_of_scope
- `notes`

### `council_forms`

- `form_id`
- `service_id`
- `url`
- `source_id`
- `fields`: name, label, type, required, options, conditional
- `documents`: proof of address, vehicle document, photo, other
- `fees`: amount and description, only when cited
- `eligibility_questions`
- `form_hash`
- `checked_date`

### `council_rules`

- `rule_id`
- `service_id`
- `condition`
- `outcome`
- `question_field`
- `explanation`
- `source_id`
- `quote`
- `checked_date`

Rules are extracted from a checked page or form. If a rule cannot be tied to a source and a quote, it is not used.

### `council_evidence`

- `evidence_id`
- `service_id`
- `fact`
- `quote`
- `source_id`
- `url`
- `checked_date`
- `caveat`

### Existing task tables

The current tasks table stays. Add `task_events` for each specialist step, validation result, form reference and status change. The task page and `/council/tasks` read the same records.

## Ingestion pipeline

1. **Discover.** Start from the council A-Z, report-an-issue, bins, parking, housing and council tax sections, the public sitemap and the existing fact sheet. Record every public service URL and form URL.
2. **Fetch.** One request at a time, respect `robots.txt`, set a user agent and store the HTTP status, timestamp, content hash and a snapshot. Do not scrape behind a login, captcha or payment.
3. **Extract.** Parse HTML and PDF text. Candidate fields, rules, fees and documents are extracted into `needs_review`.
4. **Review.** A human confirms each service, form and rule against the source quote. Only `verified` rows are served to the agent.
5. **Publish.** The specialist reads only verified rows. A missing or stale source becomes `unknown`, not a guess.
6. **Refresh.** Re-fetch on a schedule, compare hashes and flag changed forms. A changed form puts the service back into review.

## Eligibility and validation

Eligibility is a specialist responsibility, not a model guess.

- The specialist loads the verified rules for the service.
- It maps the resident's answers to the rule questions one at a time.
- A rule evaluates to pass, fail or unknown.
- If any required rule is unknown, the specialist says it cannot confirm eligibility and points to the official page or asks the field that decides it.
- A failed rule stops task creation and explains the failing rule with its source.
- A task is prepared only when all required fields and rules are known.
- The task records each validation result and its evidence.

This is deterministic rule evaluation over checked rules. It is not a classifier and not invented policy. The LLM may choose to call the specialist, but the rule outcome is explicit.

## Flow with the frozen director

1. The resident sends a message or a photo.
2. The frozen director decides whether to answer, ask, capture or call a specialist.
3. The specialist returns its structured result.
4. The director asks one missing field at a time.
5. The task records the answers.
6. The specialist validates fields and eligibility.
7. A prepared case and reference are created only when validation passes.
8. The writer says what happened, with the evidence and the honest submission state.

No changes to the director prompt, writer prompt, plan schema or evidence rules are allowed without an explicit operator exception. If the existing `specialist_request` contract is insufficient, the implementation stops and asks.

## Phases

### Phase A: inventory and source store

- Build the source and service catalogue for the existing 22 categories first.
- Record page URL, form URL, checked date, snapshot and review status.
- Produce a coverage report: discovered, verified, needs review, out of scope.

Done when every existing category has a verified service or an explicit no-form/out-of-scope decision.

### Phase B: forms and fields

- Parse the 4 known online forms and any forms discovered in Phase A.
- Record fields, required documents, fees and conditional questions.
- Add form hash and change detection.

Done when the existing categories have a form-field inventory and every field has a source.

### Phase C: rules and validation

- Extract eligibility rules for parking permits, council tax discounts, bins and housing repairs.
- Implement the rule evaluator with pass, fail and unknown.
- Add validation to the task flow.

Done when a permit application can be checked against the published eligibility rules and an ineligible case is refused with a cited reason.

### Phase D: specialists

- Implement the four specialist tools.
- Route the existing `specialist_request` groups to them.
- Add one question per turn and specialist result tests.

Done when the director can call each specialist and the result carries evidence, fields and eligibility.

### Phase E: catalogue expansion

- Expand discovery beyond the 22 categories to the wider resident-facing catalogue.
- Keep the coverage report current.
- Mark unsupported services honestly.

Done when the catalogue lists every discovered public service and its verification state.

## Acceptance

- Every served fact, rule and form field has a URL and checked date.
- No rule, fee or timescale without a source quote.
- A specialist can say "not eligible" and explain the rule.
- A specialist can say "unknown" rather than guess.
- The task page and `/council/tasks` show the specialist, fields, reference and validation.
- The frozen LLM files are unchanged.
- Tests cover: allowed service, ineligible service, missing field, unknown rule, changed form, stale source and no-form service.
- A coverage report exists and is readable by the team.

## Risks

- The council site has hundreds of services; "all" needs a reviewed boundary.
- Some forms need login, payment, captcha or JavaScript; record them as manual links.
- PDFs and old pages may be inconsistent.
- Rules can change without notice; change detection and review are mandatory.
- Council permission may be needed for regular fetching.
- No direct submission without a council integration or Chromeflow demo, which is out of scope here.

## Open questions

1. Confirm "all" means all public resident-facing report, apply, request and permit services, not internal council work.
    yes resident facing
2. Which four specialists are the right cut, or should council tax be separate from housing?
3. Is a human review step acceptable for each new service before it is used?
    not required atm
4. Which forms may be fetched and parsed without permission?
    all
5. How often should the catalogue refresh?
    once rn
6. Do we need a council contact for the source permission before the demo?
    no

the specialists should be able to handle all the forms and stuff, but also general information like when is my bin collection day
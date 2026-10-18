# Agentic vision for Kerbside

Status: plan only. No feature work until this is approved. The current web app must stay stable while this is built.

## The idea

The first messages should feel like a person from the council, not a chatbot. The resident should be able to send text, a photo or a location without being told to pick a category. Once the conversation shows what they need, a specialist layer pulls the real rules, forms and evidence for that area. The reply still sounds human, but it is backed by a specialised workflow. This does not mean it is deterministic.

The system is not a classifier. The model reads the whole conversation, decides what the resident needs and calls tools. The locatino tool should be called within the first 3 messages. Regexes do not route intents. Deterministic code only protects safety. Apart from this we do not require deterministic code.

## Onboarding

1. The first line is human and short: `hey, this is soton council. what can we help with?`
    IF the user has already onboarded, then this message isnt required, also the user always messages first. also have non deterministic variations of this, so if seperate people message, they see different things.
2. No name, address or phone at the start. Accessibility first.
    es we want to make it as easy as possible for people to take a photo and report it.
3. The resident sends text, a photo or a location. The graph captures it and sends the location link when a report has no location.
    yes request link instead of asking for location since that is inaccurate
4. After the problem is saved, the reply may ask one optional question: `thanks, can we add a name to this report?` only if nothing more urgent is pending.
    name isn't required at all for report. only ask for name if name is required for filling out form
5. Profile fields are collected when a task needs them, one question at a time.

## Director, not classifier

One director call per turn receives:

- the whole stored conversation, resident and agent
- the profile and stored style
- the active report, draft and pending question
- the available tools and the current specialist context

It returns one typed plan: intent, action, incident patch, profile patch, one clarification, one tool call. Examples: `save_report`, `get_status`, `request_location`, `attach_photo`, `start_task`, `ask_task_field`, `specialise`.

The writer receives the executed outcome and writes in the resident's register. A model failure falls back to the last checked template so the turn never dies silently.

## Evidence, not vibes

A specialist must answer with evidence. The evidence service:

- crawls the relevant Southampton pages on a schedule
- stores URL, fetched date, content hash, page title and extracted facts
- keeps a versioned snapshot so a fact can be traced to a page and a date
- returns facts with citations to the specialist and writer


## Specialist subagents

Specialists are pulled in by a tool call from the director, not by a keyword match.

- **Permits and parking**: parking rules, resident permits, visitor permits, suspensions, appeals. Tools: search rules, check eligibility, collect fields, prepare a draft application, return a reference and status.
- **Council tax**: discounts, bands, exemptions, payment support. Tools: search policy, collect facts, point to the official form.
- **Bins and waste**: collection days, missed bins, assisted collections. Needs a verified schedule or council API. Without it, say the data is not connected.
- **Reports**: the current capture and location workflow stays.
There should be more information from the council, if not scrape as much as possible - the mayor has given permission.

Each specialist returns facts, missing fields, citations and a recommended next action. It never speaks to the resident directly. The writer keeps one voice.

## Agentic tasks

A `tasks` table holds real work, not chat:

- `task_id`, `kind`, `status`, `fields`, `resident_ref`, `created_at`, `updated_at`
- `task_events` for each tool step
- a private task link `/t/<token>`

The permit is the first showcase:

1. the director recognises a permit need
2. it asks one required field at a time
    it asks in a human like format
3. it checks eligibility against the evidence
4. it submits application and gives a reference
    but theoretically should submit for you and go directly into the council system
.

## Personal updates

Personal bin updates such as "your collection is a day later" need a verified data source. The current fact sheet does not contain per-address calendars. Do not invent one. Connect a council API or an approved schedule file, label demo data clearly, and only then personalise.

Focus on personalising by neighbourhood or address. Can be irregular. This is not a required feature.

## Memory and style

- Every resident and agent message is stored and loaded into the next turn.
- The profile stores name, address, phone and style, only when offered or needed.
- The style can be casual, formal or neutral and follows the resident.
- Conversation history survives a restart; a new page load starts a fresh chat in the web app.

## Phases

if fisrt time user:
- start of with problem or solution - jump right in if person gives proble
- if greeting then give what u do as in intro
- if confusion or questions, then answer those questions
- as convo gets bigger and agent is used more, more information can be stored, remembered and collected about the person so the agent can be more useful over team esp in repeated tasks

-if person is messaging after alr interacting, then just ask whats up or similar whatever is suitable to their tone 

## What not to do

- No keyword classifier for intent.
- No canned intro that sounds like a bot.
- No name, address or phone at the start of a conversation.

## Real backend connection

There is no public council case API to pretend we have. The honest way to show a real workflow is an adapter with two implementations behind the same tools.

### Existing dashboard and council integration stay

The dashboard and the council-facing integration already built are the council
console. Do not rebuild them. The adapter writes a case and its events into the
existing store, and the dashboard reads the same case. The resident page and the
council page keep their current shape.

Chromeflow is the demo rail, not the product architecture. It drives the real public
form in a browser and captures the evidence that a direct council integration would
later capture through an API. The same adapter boundary is what the council plugs
into. In the demo we say: this is the workflow, the adapter is the seam, and today
Chromeflow is standing in for the council's system until the integration is live.

### What the demo shows

Split screen: the resident chat, the council dashboard and the audit log.

1. Resident asks for a parking permit.
2. The permit specialist collects name, address and vehicle, one question at a time.
3. `create_case` calls the adapter. The audit log shows the request, response and external reference.
4. The dashboard shows the case. An officer changes the status to approved.
5. The webhook reaches the agent, which sends the resident a private status update.
6. The resident link shows the same case and status.

That is the proof: a tool call, an external reference, an officer action and a resident update. Not a chat message claiming it happened.

### Guardrails

- Consent before a real form is filled or submitted.
- No submission without a human confirmation step.
- No invented reference or status.
- One case per request, idempotent by turn id.
- Test data only, and a clear sandbox label where used.
- Rate limits and no bulk submissions.

## Open questions

1. Which council pages may be crawled, and how often?
    i wish all of them but we r on time limit so whatever would be bet to demo. if we have time we can add others 
2. Which permit types are in scope for the demo?
    i wish all of them but we r on time limit so whatever would be bet to demo. if we have time we can add others
3. Is there a bin schedule API or an approved data file?
    how am i supposed to know though
4. Does any task ever submit to a council form, or does it always prepare a draft and hand over?
    - always submit since integrated to council system
5. Which fields does the permit task really require, and which can be optional?
    no idea

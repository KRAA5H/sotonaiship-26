# RAG and resident messages, phase 1

Plan mode. Nothing built yet. This replaces phase 1 of `plans/finish.md`; everything else waits.

## Context

The bot currently answers in boilerplate. A pothole gets "Thanks, that is logged with the council (Pothole)" and a link. A "thanks" gets a refusal, because every message is forced through triage. A question about a fact gets one canned sentence even when the rulebook holds a better one. None of it cites anything.

Instinct, the iMessage agent everyone is copying, wins on message discipline rather than model quality. Its own reviewers describe the same habits: it finishes jobs instead of stopping to confirm, it answers its own questions from what it already has, it reacts instead of replying when a reply would be noise, it says what happens next when it hits a wall, and it keeps one thread with persistent context. That is the bar for a council text line, minus the parts of Instinct we should not copy.

## What we copy, and what each becomes

| Instinct habit | What we build |
|---|---|
| Finishes the job instead of confirming | Log the report first, then ask the one thing only the resident knows. A missing street no longer throws the report away, it saves it as incomplete and fills it in on reply |
| Answers its own question | Category, severity, team, ownership and the official link come from the rulebook, never from the resident |
| One continuous thread | A status question is answered from the database against that sender's latest report. No re-explaining, no link hunting |
| Reaction instead of noise | Greetings and thanks do not get a refusal. Thanks gets silence, a greeting gets three examples of what it can log |
| Says what happens next at a wall | Out of area, motorway and utility problems get the confirmed contact and number from `guidance_links`, not a Google search |
| Human, short, in the same tone every time | One module owns every resident-facing string, with copy rules enforced by tests |

## What we do not copy

No acting on the resident's behalf beyond logging a report. No silent sends. No retaining message history past the report and its link. Instinct's week one produced an unapproved email and inbox copies kept after disconnect; our conservative choices are a feature, and the plan says so in the README rather than pretending otherwise.

## Approach

### Vector database, or plain context?

Plain context. Measured, not guessed: all 53 dated facts are 11,750 characters, about 2,940 tokens. With the category menu the whole system prompt is about 3,770 tokens, which is 0.11 pence uncached and 0.002 pence on a cache hit at published DeepSeek prices. A vector database would need an embedding model, and DeepSeek does not publish one, so it would mean a second provider, a second key and a new failure mode for no measurable gain on 50 documents.

No example files to download for retrieval. The 60 real reports in the evaluation are for measuring accuracy, not for embedding. The corpus is the 53 facts we already have, each with a source and a date checked.

Context can break in four ways, and each has a guard that costs nothing:

| How it breaks | Guard |
|---|---|
| The model blends or ignores facts in a wall of text | Inject only the top 3 relevant facts, not all 53, and say "answer only from these" |
| It invents a URL or a number | We strip model-written URLs and append the source line ourselves |
| A resident writes "ignore your instructions" | Facts live in the system message, the message is passed as data, and an injection test is in the suite |
| A fact is stale | Every fact carries `date_checked` and a URL, and the reply shows the date |

What makes retrieval honest is the evaluation: 12 questions with a known correct fact, scored at retrieval@1 and @3. If that ever drops below 10 of 12, we revisit embeddings. It is a decision with a trigger, not a preference.

### 1. Retrieval over the checked facts (`code/rag.py`)

Corpus: the 53 dated rows in `agent/confirmed_with_websites.csv` plus each category's `answer_facts_to_cite`, `official_form_url`, `note` and `guidance_links`, loaded through `agent/loader.load`.

- Token overlap scoring with stopwords removed, a category match boost, and a URL boost. No embeddings: DeepSeek exposes no embedding model, and keyword scoring over 50 documents is honest and debuggable.
- `retrieve(question, category_id, k=3)` returns rows with id, text, source name, url and `date_checked`. It searches the whole corpus with a category boost rather than filtering to one category first, so a question that crosses categories still finds its fact.
- The result is injected into the prompt as context. No index, no database, no download step.
- 12 hand-written resident questions with the expected fact, scored as retrieval@1 and @3.

### 2. Grounded answers with attribution we control (`code/rag.py`)

- The model writes two sentences, from the retrieved rows only. It never writes a URL.
- We append "Source: name, checked date, url" ourselves, so provenance cannot be hallucinated. Any URL in the model body that is not in the retrieved set is stripped.
- Below the score threshold: "I don't have a checked answer for that" plus the official council page. No guess.
- Wired in for info and question messages. Report acknowledgements stay factual.

### 3. One voice for every message (`code/messages.py`)

Every resident-facing string moves here: acknowledgement, duplicate, incomplete, guidance, out of area, emergency, unreadable, status, greeting, thanks.

Copy rules, enforced by tests:

- First line says what happened, not thank you.
- At most three short lines, one URL, no markdown, no jargon, no unconfirmed team names.
- Say what happens next, and promise only what the system does today. No "we will text you" until the completion text exists in phase 2.
- Echo the category and street back, so a wrong reading is obvious to the resident.
- Emergency always starts with "Call 999".

Examples of the shape, not final copy:

```
Logged: pothole, Weston Lane.
Crews treat a deep pothole in the road as urgent.
Follow it: http://192.168.0.202:5005/r/xyz
```

```
Logged: fly-tipping near 12 Alma Road, photo attached.
Where exactly is it, if I have the wrong spot? Reply and I'll fix it.
```

### 4. Act first, then ask

When triage says the category is a council report but the location is missing, `save_report` runs anyway with location "Not given" and the reply asks for the street. The pending memory already exists and now carries the report id and token, so the resident's answer updates that row instead of creating a second report. An officer sees an incomplete card, which is the truthful state.

### 5. Thread memory and status

- `reports_db.latest_report_for(reporter_ref)` and a status intent check: update, status, fixed, done, any news, what is happening.
- Answer with the status in plain words, the street, and the link. If the report is resolved and the resident says it is still there, log a new report linked to the original.
- No model call for this path, so it is instant and cannot invent anything.

### 6. Message evaluation (`code/eval/messages.py`)

18 scripted resident messages, run offline with a fake model, each with expected properties: which path, what must appear, what must not, and a length ceiling. Examples: a thanks gets no refusal, an out-of-area message names the right contact and no Google link, an info answer contains a Source line with a real URL from the retrieved row, an emergency starts with 999.

This is the "as effective as possible" evidence: a pass rate, not an opinion. It runs in the same suite as the rest.

## Files

- New: `code/rag.py`, `code/messages.py`, `code/test_rag.py`, `code/test_messages.py`, `code/eval/rag_cases.csv`, `code/eval/messages.py`
- Changed: `code/blue_bubbles.py` (paths and wiring), `code/triage.py` (drop `guidance_for`, keep the emergency guard), `code/reports_db.py` (`latest_report_for`, `set_location`), `code/test_bot.py` (move to the new copy), `code/test_triage.py`
- Untouched: `code/tools.py`, `code/bb.py`, schema, website, `agent/categories.json`

## Reuse

- `agent/loader.load` already joins rules to the dated facts.
- `guidance_links` in `agent/categories.json` already holds 999, National Highways and find-your-council contacts.
- `follow_up_questions` per category gives the ask-back wording, so we stop inventing generic questions.
- `merge_pending` and `remember_location` in `code/blue_bubbles.py` already handle the follow-up window; they gain the report id.
- `test_bot.DbCase`-style mocking and `unittest.mock.patch.object` keep every new test offline.

## Steps

- [x] Build the corpus and retriever, with the 12-question retrieval check
- [x] Grounded answer builder, URL stripping, threshold refusal
- [x] `messages.py` with every path and the copy rules as tests
- [x] Act first: save with "Not given", update on reply
- [x] Status intent and latest-report lookup
- [x] Emergency guard and official contacts replace search links
- [x] Wire the bot, update the existing copy tests
- [x] 18-case message evaluation, then eight scripted live texts

## Verification

| Check | Expected |
|---|---|
| "how long do potholes take to fix" | two sentences from a dated fact, Source line with url and date |
| "how do I get a parking permit" | no invented answer, official page instead |
| "thanks" | no refusal, no noise |
| "hi" | three examples of what it can log, under 300 characters |
| photo of biscuits | says what it sees, logs nothing |
| "pothole near my house" then "Alma Road" | one row, location filled in, no duplicate |
| "any update?" | current status and link, no model call |
| "smell of gas" | starts with Call 999, nothing saved |
| pothole on the M27 | National Highways contact from the rulebook, no Google link |
| message eval | 18 of 18, plus the 106 existing tests still green |

## Time

Two hours for retrieval and answers, two for messages, status and the evaluations. Live check at the end with eight scripted texts, then phase 2 from `plans/finish.md` resumes.

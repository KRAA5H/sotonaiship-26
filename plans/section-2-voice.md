# Section 2: the resident's voice

Plan for `TODO-SPLIT.md` section 2. Three scouts mapped the reply paths, the photo path and the tests. Nothing built yet.

## Context

Nine reply paths all return a fixed template from `code/messages.py`. The worst is `NOT_COUNCIL_COPY["find_your_council"]`: "That one is not Southampton City Council's to fix." The owner's feedback is that this reads automated and removes the advantage. The same applies to every other path: "I do not have a checked answer for that." three times in a row in one conversation.

Section 2 also owns three product gaps: nobody is ever asked for a photo, a photo sent later goes nowhere, and the resident page says "You sent a photo" but shows nothing.

The target register, in the owner's words: it should feel like texting a friendly young person who works at the council, not a form. Casual, warm, contractions, plain words, quick to help. Not corporate, not stiff, and never slang that will date by next week.

The register, side by side. Facts identical on both sides, only the words change.

| Path | Today | Target |
|---|---|---|
| Saved | "Logged: pothole, Weston Lane. The council has it for review. Follow it: link" | "nice one, that's logged - pothole on Weston Lane. if you can grab a photo, send it over and it'll help the crew." |
| Duplicate | "Already logged: pothole, Weston Lane. Follow it: link" | "someone's already reported that one, so i've linked yours to it. you'll both get the same updates: link" |
| Refusal | "That one is not Southampton City Council's to fix." | "ah that one's not ours, sorry. National Highways handles motorways - give them a ring on 0300 123 5000." |
| No answer | "I do not have a checked answer for that. The council's page: link" | "honestly i'm not sure on that one, but the council page will have it: link" |
| Incomplete | "Logged: pothole. Which road, and nearest house number or junction?" | "got it, pothole logged. whereabouts is it? a street and the nearest number is plenty." |
| Status | "Update on your pothole at Weston Lane. Status: being looked at by the council." | "quick update on the pothole at Weston Lane - it's being looked at by the council now. follow it here: link" |

## Approach

### 1. A voice layer with hard facts (`code/voice.py`)

One extra model call per reply, on every path. Cost and latency are accepted: the tone is the product, and we are not trading it for a second.

```python
brief(kind, facts) -> dict      # what happened, what must appear, what is banned
speak_name(category_id) -> str  # the casual name a person would use, not the database label
generate(brief) -> str | None   # one model call, JSON {"text": "..."}
lint(text, brief) -> list[str]  # [] means safe to send
say(kind, facts, template) -> str  # generate, lint, else the template
```

- The model never sees the link. We append `Follow it: <link>` ourselves, the same pattern as `rag.source_line`. One URL maximum, and the token cannot be forged.
- The model is given a **spoken name** for the category, because "litter / street needs cleaning" cannot be said out loud. A small alias map in `voice.py`, for example `pothole`, `fly-tipping`, `litter`, `noise complaint`, `bin collection`, `repair`. The lint requires the alias, and the dashboard keeps the official label.
- Required strings: the spoken category name, the street exactly as triage returned it, the status text for status replies, `National Highways` and `0300 123 5000` for motorway refusals, `999` for emergencies.
- Required meaning, at least one phrase from a short list per path: a saved report must say it is logged, noted, on the list or reported. A duplicate must say already, someone else or first. A no-answer must say not sure, do not have or cannot check. This is how a casual sentence still proves it did its job.
- Banned: URLs, phone numbers not in the facts, invented digits, `R-\d{4}`, unconfirmed team names, markdown, em dashes, "interested in", Google and search links, any promised timescale (`within 2 hours`, `will be fixed`, `guarantee`), and the corporate register: "please be advised", "we apologise for any inconvenience", "do not hesitate", "kindly", "further to your enquiry", "thank you for your patience", "I understand how you feel".
- Limits: 320 characters, three non-blank lines, four on a saved report that also asks for a photo, one question mark on the incomplete path.
- Any lint failure, an empty reply, or a model timeout falls back to today's template. Never a partial sentence, never both. Log `[voice] fallback <path> <reasons>`.
- Grounded answers from `rag.answer` keep their citation, and `rag.SYSTEM` gets the same casual register so they stop sounding like a policy document.
- Emergency keeps its fixed first line, "Call 999 now.", and the rest of that message may be voiced. Safety wording is never left to the model.

Voice applies to: saved, duplicate, incomplete, not council, no answer, unreadable, greeting, status, photo confirmation. Not to: the first line of an emergency, and thanks, which stays silent.

`llm.chat` gains optional `temperature` and `max_tokens`, and voice calls run hotter (about 0.9) and shorter, so the same message does not come back in the same words. Default behaviour unchanged, so nothing else breaks.

### 2. Ask for a photo, once, in the same text

- Every saved report without a photo gets one extra line, folded into the reply and into the link line where possible. Never a second message. Something like "if you can grab a photo, that'd help the crew".
- The template fallback gains the same line, and the line limit for those two paths goes from three to four. `test_messages.py` is updated to say four on the saved and duplicate paths only.
- Existing behaviour that says "Photo attached." when a photo was sent stays.

### 3. A photo sent later attaches to the open report

- New `reports_db.open_reports_for(reporter_ref)`: that sender's unresolved reports with no photo, newest first, limit three.
- Attach only when all of these hold: the message has no text, one image attachment, exactly one candidate row within 72 hours, and the attachment is not a plugin payload (Apple Maps pins must not be treated as photos).
- The in-memory pending entry wins when we have one, because it already holds the report id.
- Write with `UPDATE ... WHERE id = ? AND photo_guid IS NULL`, so a replayed webhook cannot overwrite, and set `has_photo = 1` in the same statement.
- Reply is one short confirmation, never a second photo request.

### 4. The resident sees their own photo

- The photo stays where it is and we store a reference to it, not the bytes in SQL. Two columns: `photo_guid TEXT, photo_mime TEXT`. Additive `ALTER TABLE` migration inside `init_db`, driven by `PRAGMA table_info`, safe on the populated file and idempotent. 36 legacy rows have `has_photo = 1` with no guid, so every display path tolerates "says photo, has none".
- New `code/photos.py` with a nested Blueprint registered on the existing `site`, so the private headers and the same port apply. One import line in `blue_bubbles.py`, zero edits to `website.py`, which Section 3 owns.
- `GET /r/<token>/photo`: the token is the only key. Unknown token or missing guid is a 404, never a 403. Fetches through `bb.download_attachment`, but only to return bytes. `Content-Type` whitelisted to jpeg or png, `Cache-Control: no-store`, `no-referrer`, `nosniff`, no ETag, and the guid never appears in a URL.
- `tools.get_report_status` returns `photo_url` when a guid exists, never the guid itself.
- `resident.html` gains a photo section and the detail row becomes photo, then "You sent a photo", then "No photo". No scripts, since the page is asserted script-free.

## Files

| Owner | Files |
|---|---|
| Worker A | `code/voice.py` (new), `code/test_voice.py` (new) |
| Worker B | `code/photos.py` (new), `code/reports_db.py`, `dashboard/schema.sql`, `dashboard/SCHEMA.md`, `code/web/templates/resident.html` |
| Me | `code/messages.py`, `code/blue_bubbles.py`, `code/llm.py`, `code/rag.py` (tone only), `code/tools.py`, `code/eval/messages.py`, `code/test_bot.py`, `code/test_messages.py`, `code/test_website.py` |

One writer per file. A and B run in parallel on disjoint files. I wire the seam afterwards, so nothing fights over `blue_bubbles.py`.

## Reuse

- `messages.py` templates remain the fallback contract, untouched except the photo line.
- `rag.source_line` is the pattern for appending facts we control.
- `llm.chat` handles the provider ladder; the voice call goes through it with a shorter budget.
- `bb.download_attachment` returns bytes and mime, already HEIC-safe.
- `reports_db.set_status` and `set_location` show the UPDATE-and-rowcount pattern for `set_photo`.
- `tools.reporter_ref` is the only way the photo attach finds the sender's reports.
- `test_bot.py` already fakes `save_report` and the database, so the new paths slot into it.

## Steps

- [x] Worker A: `voice.py` with `brief`, `generate`, `lint`, `say`, and the style prompt; `test_voice.py` with 20 offline cases, including every lint rule and the timeout fallback
- [x] Worker B: schema columns and migration, `set_photo`, `open_reports_for`, `photos.py` route, resident template and detail row, tests for the route and the migration
- [x] Me: optional `temperature` and `max_tokens` on `llm.chat`
- [x] Me: wire `reply_for` to the voice seam on all nine paths, with templates as fallback
- [x] Me: photo ask on the saved and duplicate paths, template and voice
- [x] Me: late photo attach in `handle_inbound` before triage
- [x] Me: `photo_url` in `get_report_status`, resident template bound to it
- [x] Me: update the five broken bot tests to assert facts rather than wording
- [x] Me: ten new eval cases, run twice, templates only and voice on
- [x] All: six scripted live texts and one late photo through the real server

## Verification

| Check | Expected |
|---|---|
| Refusal | casual and human ("ah that one's not ours, but National Highways will sort it"), correct contact, no search link |
| Saved report | casual, says it is logged, names the problem and street, asks for a photo, four lines maximum, one URL |
| No answered question | casual, admits it does not know, points at the council page |
| Same message twice | wording differs, facts identical, both contain the link once |
| Corporate phrase ("please be advised", "do not hesitate") | lint rejects, template is sent instead |
| Invented time ("within 2 hours") | lint rejects, template, `[voice] fallback` in the log |
| Unconfirmed team ("Highways Team will repair it") | rejected, template |
| Photo sent later | attached to the open report, `has_photo = 1`, confirmation with the link |
| Resident page | the photo renders, 404 for a bad token, no guid in any URL except `/r/<token>/photo` |
| Legacy rows | "You sent a photo" with no broken image |
| Emergency | still starts with "Call 999 now.", never model-written |
| Existing suites | `test_bot`, `test_messages`, `test_tools`, `test_website`, `test_triage`, `test_rag` all pass |
| Live | six texts and one photo, transcript in the worklog, before and after side by side |

## Coordination, and the one contract change

`reports_db.py` belongs to Section 3 in the split, and `blue_bubbles.py` to Section 1. Two surgical touches are unavoidable: the photo columns and their migration, and one import line to register the photo blueprint. Both go into `DECISIONS.md` as a signed contract change so section 3 builds its cards on the same fields.

## Decisions taken

1. Voice on every path except the emergency first line and thanks. Cost and latency accepted; one extra model call per reply.
2. The register is a friendly young council employee. Casual, contractions, helpful, no corporate phrasing. The exact examples in `voice.py` are the contract.
3. Photos stay as BlueBubbles file references. Two reference columns, no image bytes in SQL.
4. Wording varies, facts do not. A test proves two runs differ while the fact signature stays identical.

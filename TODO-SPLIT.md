# Open work, split three ways

Written Sat 17 Oct 2026, 20:30. Every item below comes from real traffic through the live bot on port 5005, not from reading the code.

Read the evidence before starting: the transcript is in `WORKLOG.md` under 21:40, and the affected rows are `R-0070` to `R-0078` in `code/kerbside.db`.

## The rule for all three sections

One owner per file. If you need a change in someone else's file, write it in `DECISIONS.md` and message them. `main` must stay runnable, which means `python code/test_bot.py`, `python code/test_tools.py`, `python code/test_triage.py`, `python code/test_website.py`, `python code/test_rag.py` and `python code/test_messages.py` all pass before you push.

Each section ends with a test that fails today and passes after.

---

# Section 1: Intake, speed and shared location

Owner: the iMessage and model path. Files: `code/blue_bubbles.py`, `code/bb.py`, `code/llm.py`, `code/triage.py`, `code/rag.py`.

## 1.1 Shared Apple iMessage location becomes a street

Evidence. At 20:08 a resident sent an Apple Maps pin. It arrived as text `https://maps.apple.com/place?coordinate=50.906932,-1.405823&name=Dropped%20Pin` with two `.pluginPayloadAttachment` files. The bot replied "I could not read that."

The coordinates are in the plain text, so no payload decoding is needed. A live reverse lookup on OpenStreetMap Nominatim returned "Windsor Terrace, Cultural Quarter, The Polygon, Southampton, SO14 7BQ" in one keyless call.

- [ ] Parse `coordinate=lat,lon` out of any message text, plus the `/place`, `/search` and bare map URL forms
- [ ] Reverse geocode with Nominatim: one call, cached by rounded coordinate, a real User-Agent, at most one request per second
- [ ] Use the result as the location, street plus nearby landmark plus postcode
- [ ] A pin carries no words, so when a location arrives with no category, ask only what the problem is and keep the location
- [ ] Check the postcode is in Southampton, and refuse politely when it is not
- [ ] Never store coordinates, only the street. Never send the pin to anything except the geocoder
- [ ] Test: the exact pin text above produces "Windsor Terrace" and no "I could not read that"

## 1.2 The follow-up loses the category

Evidence. `R-0074` was fly-tipping with no street. The resident replied "lawn road" and the bot saved `R-0075` as `unclear_other`, because triage was re-run on the joined text and answered badly. The pending record holds the report id and link but not the category, so the guard that should have caught this never fired.

- [ ] A pending report keeps its category, and a follow-up only supplies the missing field
- [ ] When a follow-up has no usable category of its own, keep the original one
- [ ] Test: `R-0074` style flow, "there is a chair on the street" then "lawn road", produces one row, fly-tipping, Lawn Road

## 1.3 A fragment must not become a refusal

Evidence. The same "lawn road" message produced `outside_southampton` and the reply "That one is not Southampton City Council's to fix." Lawn Road is in Southampton.

- [ ] Do not decide "outside Southampton" from a short message with no place evidence
- [ ] Require a postcode or a named place outside the city before that conclusion
- [ ] Test: "lawn road" never yields `outside_southampton`

## 1.4 Never link two reports still waiting for a street

Evidence. `R-0076` (Rigby Road) and `R-0077` (Lawn Road) are flagged as duplicates of each other. Both were saved with `location = 'Not given'`, so they matched on the placeholder.

- [ ] Duplicate matching runs on the final location, never on `Not given`
- [ ] Two incomplete reports are never duplicates of each other
- [ ] Test: two different streets, both starting incomplete, end up unlinked

## 1.5 Severity is missing when the model is unsure

Evidence. `R-0073`, `R-0075` and `R-0076` have `severity = NULL`. `categories.json` carries `severity_hints` per category and nothing reads them.

- [ ] When the model returns null, derive severity from the category's `severity_hints` and the description
- [ ] Never leave severity null for a council report
- [ ] Test: a pothole report with no explicit severity gets a non-null severity

## 1.6 Speed under load

Evidence. One unbounded thread per message, one to three sequential model calls per message, `TIMEOUT = 30` with two attempts, and sleeps of 0.5, 1.0 and 1.2 seconds inside the provider ladder. Ten simultaneous texters would queue behind each other.

- [ ] A bounded worker pool of four threads instead of one thread per message
- [ ] One model call on the happy path: decide "question or report" inside the triage call instead of a second `rag.answer` call
- [ ] Cut the ladder sleeps to 0.25 seconds, and skip the retry when the first reply is a clean 200 with empty content
- [ ] Log time to first reply per path, so p50 and p95 can be quoted
- [ ] Measure ten simultaneous webhooks before and after, and put both numbers in `NUMBERS.md`

## 1.7 A photo with words must always save

Evidence. "Saw graffiti on a wall" arrived with a jpeg and logged nothing, because the category came back as not-a-report. A photo plus a category should always produce a report, or a request for the street.

- [ ] A photo with a council category saves, using the ask-for-street path when the street is missing
- [ ] Non-image attachments (the maps plugin payload) are detected as a location, not as a photo
- [ ] A message with no text and no image gets the unclear reply without a model call
- [ ] Fix the log line that runs "[inbound] ... attachments=0[pending] joined a follow-up" together on one line

---

# Section 2: The resident's words

Owner: the voice of the product. Files: `code/messages.py`, `code/test_messages.py`, `code/eval/messages.py`, and the copy section of `code/web/templates/resident.html`.

## 2.1 Stop sounding automated

The feedback, verbatim: "instead of very fixed responses, we do not want automated boring responses that take away from it massively". Today every string is a template. "That one is not Southampton City Council's to fix." is the worst of them.

The right shape is closer to: "Unfortunately that one isn't ours to fix, but here's a link that should help."

- [ ] The model writes the sentence. We keep the facts: category, street, status, one link, source and date
- [ ] A warmth pass over the refusal, no-answer, duplicate and incomplete paths first, since those sound the most robotic
- [ ] Vary phrasing between identical inputs, but never invent a fact, a link or a telephone number
- [ ] Allow up to three sentences where warmth helps, never a wall of text
- [ ] Turn the existing copy rules into a lint over generated text: three lines, one URL, no markdown, no unconfirmed team names, no em dashes
- [ ] Fall back to today's template when generated text fails the lint, so the bot can never send something broken
- [ ] Extend `code/eval/messages.py` with a style check: no two replies to the same question identical, and none containing the banned phrases
- [ ] Record the before and after side by side in the pull request, so the improvement is visible in one screen

## 2.2 Ask for a photo

Evidence. `has_photo` is 0 on every real report from `R-0070` to `R-0078`. Photo analysis is our strongest evidence and we never ask for it.

- [ ] Ask for a photo on every council report that has none, as one extra line in the same reply
- [ ] Accept a photo sent later and attach it to the open report
- [ ] Never block a report on a photo. The report is already logged, the photo only improves it
- [ ] Keep it to three lines and one URL: confirmation first, then the ask, then the link
- [ ] Track the share of reports with a photo so `NUMBERS.md` can show the improvement

## 2.3 The resident page

Files: `code/web/templates/resident.html` only, coordinate with Section 3 before touching the route.

- [ ] Show the resident's own photo on their report page, if they sent one
- [ ] The completion text copy for when a report moves to resolved, matching the warmer voice
- [ ] One plain sentence at the top saying what happens next and when

---

# Section 3: The officer's view and the numbers

Owner: the dashboard, the scoring and the evidence. Files: `code/website.py`, `code/web/templates/council.html`, `code/web/static/kerbside.css`, `code/priority.py` (new), `code/reports_db.py`, `NUMBERS.md`.

## 3.1 Photos on the council card

- [ ] The photo on every card that has one, click to enlarge
- [ ] Say clearly when there is no photo, rather than showing an empty space
- [ ] Never show a model-written description as if it were the officer's own note

## 3.2 Summary statistics

Two of the five numbers we are judged on are currently invisible.

- [ ] A summary strip above the list: total open, by category, by severity, with a photo, duplicates caught, average time from report to first status change
- [ ] Computed from `kerbside.db` at request time, never hardcoded
- [ ] The same figures exportable as CSV for `NUMBERS.md`
- [ ] Synthetic rows labelled synthetic on the page, as the rules require

## 3.3 Priority with visible factors

- [ ] `code/priority.py`, pure functions, score computed on read so there is no migration
- [ ] Severity, exposure from the category group, cluster count, and age in days
- [ ] The card shows the four factors, not just the score. A score nobody can explain is a black box
- [ ] The photo's structured features feed severity once Section 1 lands them

## 3.4 Structured photo analysis

- [ ] A fixed shape from every photo: what is visible, estimated size, surface (road, pavement, private land), hazard, and a short label
- [ ] Stored on the report so the officer sees features, not prose
- [ ] Feed those features into the priority score
- [ ] Keep DeepSeek V4.1 Flash as the vision model, which already works and costs nothing extra, and compare one stronger option on the same ten photos before switching
- [ ] Never let a photo description invent a location

## 3.5 The evaluation and `NUMBERS.md`

- [ ] `NUMBERS.md` exists, with one table and a source and date on every row
- [ ] Category accuracy against the keyword baseline, on 60 real Southampton reports
- [ ] Duplicate catch rate plus false positives, on real same-street pairs and hard negatives
- [ ] Cost per report measured from usage, not guessed
- [ ] Report the losses, not only the wins. A table with no losses reads as a sales sheet

---

## Order I would suggest

Section 1 first for 1.2, 1.3, 1.4 and 1.5, because they are producing wrong rows in front of judges. Section 2 in parallel, since it touches no shared file. Section 3 last, because the summary stats are worth more once the data is right and the photos exist.

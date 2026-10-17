# Kerbside: the plan

**SotonShip 2026, Southampton City track. Written Sat 17 Oct 2026, 15:10. Lock is Sun 18 Oct 13:00. That is 22 hours.**

Working name: **Kerbside**. Alternates: Tideline (if we lean coastal), Fixline (risky, reads as a FixMyStreet clone).

---

## 0. The verdict, in one paragraph

The pitch is not "AI triages council reports". That is the organisers' own example and earns nothing extra. The pitch is **the council's front door moved into the place residents already live**: you text a number, a photo and a sentence, and by the time you have put your phone away the job is on a crew's list for tomorrow with the right kit, the right priority and the right owner of the land. The AI is what makes that possible: it holds the conversation, reads the photo, decides whether it is the 40th report of the same pothole, works out whether the council even owns that verge, then executes every downstream step itself. The differentiator is the **end of the chain**, not the start. Everyone stops at "routes it to the right team". We stop at "booked, scheduled, and the resident gets a text when it is done".

One-sentence test, filling the brief's own template:

> We help **Southampton City Council's street-scene and coastal teams** to **turn residents' messages into scheduled, deduplicated work orders on tomorrow's list** across **the city** using **a conversational agent, vision triage and weather-driven scheduling**.

---

## 1. What we verified today, before planning anything

Never plan on a link someone else gave you. Checked by request from this machine, Sat 17 Oct 2026:

| Thing | Result | Consequence for the plan |
|---|---|---|
| `fixmystreet.com/open311/v2/requests.json` | **200, real JSON**, national reports with description, lat/long, photo URL, service name, agency, timestamps. 1000 records per response cap, and it rate limits (returns an HTML error page if you hammer it) | Use it. Paginate in 3-day windows with 2s backoff, filter by Southampton bbox client-side. This is our real test set |
| `api.open-meteo.com/v1/forecast` | 200, keyless, hourly soil temperature at 6cm, soil moisture, rain, wind, plus `past_days` history | Grass-growth and leaf-risk index with no key, no signup, no quota story |
| `marine-api.open-meteo.com/v1/marine` with `sea_level_height_msl` | **200, keyless tide height and wave height** for Southampton Water | The coastal module needs no UKHO key and no EA tide gauge. It is a model, not an observation, so we say so |
| `flood-api.open-meteo.com/v1/flood` | 200, keyless river discharge forecast (GloFAS) for the Itchen/Test | Tidal plus fluvial risk on one screen, both live |
| EA flood-monitoring warnings, Hampshire | 200, **0 warnings** on a dry evening | Do not build the demo around a live flood warning. Build it around tide plus rain, which always has data. The empty warnings response is our "missing data" failure case, handed to us for free |
| Southampton report portal | `southampton.portal.uk.empro.verintcloudservices.com`, an **Empro (Verint)** portal with a separate form per issue type | The council already has a taxonomy we can mirror. Integration target one |
| Southampton highways delivery | **Balfour Beatty** Southampton Highways Partnership, awarded Oct 2025 on the SCAPE framework; the council historically ran **Causeway Confirm** for highways asset management | "Today list" means a Confirm work order on a Balfour Beatty crew's list. Integration target two |
| BlueBubbles | Requires a **macOS host** running the server app. Send is `POST /api/v1/message/text` with `{chatGuid, text, method}` (private-api or apple-script), auth by `?password=`. Webhooks POST `{type, data}` with `data.chats[0].guid`, `data.isFromMe`, `data.text` | The Mac question is the single biggest technical risk. Gate it in the first hour, and see the fallback ladder in section 9 |

**Note on the stray "coastal authority" message.** Treated as accidental. But the coastal data is free and already verified, so it stays as **Module C**, a thin optional layer that makes the same predictive engine worth more to a coastal council. It costs about 90 minutes and it opens the second-city story to Portsmouth and BCP, both coastal and both on the same class of systems. Keep it, do not let it become the spine.

---

## 2. Why this scores

| Criterion | Weight | Our evidence |
|---|---|---|
| C1 Problem and user | 20% | 10,948 fly-tipping incidents in Southampton in the year to March 2024, highest in Hampshire; rate rising 37.6 to 42.7 to 47.1 per 1,000; 61% on council-owned land; £830,000 already allocated to pothole crews. Plus: the council publishes one form per issue type on a portal nobody opens on a phone, which is why 755 fly-tipping cases sat open on FixMyStreet. Named user: a street-scene officer, and behind them a resident who will not install an app |
| C2 AI at the core | 20% | Three separate AI steps, each with a stated dumb baseline and a measured comparison on real Southampton data (section 5). Remove the AI and you are left with a keyword list that cannot read a photo, cannot hold a five-turn conversation, and cannot decide that two reports 40 metres apart are the same pothole |
| C3 Working product | 25% | Full loop on real data: real FixMyStreet report in, real Open-Meteo forecast in, work order out, resident text back out. One command to run. Two failure cases in the video (below) |
| C4 Business and scale | 20% | Buyer is the council or its highways contractor, both already spending on the problem. £0.006 of inference per report against 2.5 minutes of officer time. Second city is a taxonomy mapping file plus an adapter, 2 to 4 weeks |
| C5 Responsibility | 15% | No name, no account, no ID. Only the message and the photo reach the model, never the phone number. Every agent action audited. Low confidence goes to a human, never to a guess. Safety and flood guidance links to the EA and to 999, never written by us |

The thing that decides Stage 1 is different from the thing that decides Stage 2. Stage 1 is 70% audience money, so the demo has to land in 30 seconds: **put a phone on the table and let the room text a report to it.** Stage 2 gives the panel their own input to a 2 minute live demo, which a conversational front door survives by design. A form does not.

---

## 3. The product

### 3.1 Resident side (iMessage)

1. Resident texts the number: photo plus "this has been here weeks, near the school".
2. Agent replies in one short message, asks only for what is missing (usually the exact location), never a wall of questions.
3. Capture is capped at 5 turns. If it still lacks something, it submits what it has and says so honestly.
4. Resident gets a reference number and a plain expectation ("we have logged this, priority: urgent, you will hear by Tuesday").
5. Resident can text "status AB12" at any time.
6. When the crew closes the job, the resident gets "the pothole on Weston Lane has been repaired". When it is rejected, they get the reason and who does own it.

No app. No account. No password. Works on a lock screen. Voice notes accepted (transcribed). Video accepted if there is time, using first frame plus transcript, clearly labelled as a partial read.

A second, bounded door in the same chat: answers about **the report or the service it touches** ("who fixes this?", "what happens next?", "the drains on my road flood every tide, is that the council?"), answered only from a small curated set of official Southampton pages fetched with dates, with the citation and link attached. Bound it tightly on purpose: the brief excludes a general chatbot about Southampton, and a narrow, grounded, cited answer is not one.

### 3.2 Officer side

A single console, three panes:

- **Inbox**: live reports as they land, with the agent's category, severity, confidence, and what it decided to do.
- **Today / Tomorrow list**: capacity-aware, batched by geography, SLA due times, weather and tide flags on each job. This is the artefact a crew actually reads.
- **Job detail**: the full resident thread, the photo, the address, the asset, the duplicate cluster ("also reported by 4 people"), the audit trail of every agent action, and two buttons: **Approve** and **Override**. Override takes a reason, and the reason becomes a labelled example for the evaluation set.

A fourth, small pane: **Predictive**. Ranked work generated by the system that no resident reported. This is the Dr Gower ask, and it writes into the same Tomorrow list, not into a separate dashboard.

### 3.3 The agentic workflow, step by step

This table is the spine of the pitch. "Today" is what a human does now; "Agent" is what runs with no human in the loop; "Fallback" is what we show when it fails.

| # | Step | Today | Agent does it | Tool | Fallback |
|---|---|---|---|---|---|
| 1 | Intake and completeness | Officer reads email, works out what is missing, replies, waits days | Multi-turn agent, 5 turn cap, structured JSON end state | LLM, JSON schema | Cap hits, submit as `incomplete`, flag for human |
| 2 | Read the evidence | Officer opens photo, guesses | Vision plus text: defect type, materials, size cues, hazard cues | Vision model | Low confidence, human review queue |
| 3 | Locate | Officer copies address into another system | Postcode or landmark to lat/long, boundary check against Southampton | postcodes.io, boundary polygon | Outside boundary, honest refusal plus the right council's link |
| 4 | Whose land is it | Officer knows from experience, or a resident gets bounced for weeks | Ownership resolver: council, EA, National Highways, port, private, MOD | Asset register plus rules table | Says "a human will confirm", gives the resident the likely owner |
| 5 | Duplicate | Officer search by street, by eye | Haversine within 50m and 14 days, same category or embedding above threshold, merge into a cluster | SQL plus embeddings | Borderline, keep both and link them |
| 6 | Classify to the council's own codes | Officer picks from a drop-down | Map to Empro service name and Confirm defect code | Taxonomy file | `other`, no silent guess |
| 7 | Priority | Officer's judgement, inconsistent | Severity times exposure (school route, hospital, bus stop, tidal flood route, coast path) times report count times weather risk | Scoring function, shown as factors not a magic number | Every score shows its three inputs |
| 8 | Raise the work order | Officer retypes into Confirm | Adapter creates WO: asset, defect, location, priority, SLA due, crew, source=resident, resident ref | Mock Confirm API, plus CSV export | Adapter down, queue and export CSV, say so on screen |
| 9 | Schedule | Supervisor moves jobs around by hand | Capacity and geography aware: batch nearby jobs, respect SLA, re-optimise when something urgent arrives | Constraint scheduler | Falls back to earliest feasible slot |
| 10 | Tell the resident | Nothing, usually | Acknowledge, expectation, completion, rejection with reason | BlueBubbles send | SMS via Twilio, same text |
| 11 | Audit everything | Nothing | Every step logged: input, output, model, latency, confidence, who overrode it | Append-only log | Log write fails, job is not created |
| 12 | Learn | Nothing | Officer overrides become labelled examples in the eval set, never silent fine-tuning | Eval harness | None needed |

**This is the honest answer to "can the AI do ALL the steps":** it does 1 to 10 without a human, and the human appears at 11 and 12 as an auditor and a corrector. Do not claim full autonomy. Show the switch that turns autonomy down to "suggest only" for a council that wants it, and say why a council would start there.

---

## 4. Architecture

One repo, three processes, one command. Resist microservices.

```
resident phone / demo device
        |  iMessage (BlueBubbles webhook)  or  SMS (Twilio)  or  web chat simulator
        v
  FastAPI service  ── intake agent ── triage ── dedupe ── priority ── scheduler ── adapter
        |                                   |                                   |
     SQLite                            eval harness                        mock Confirm API
        |                                                                   plus CSV export
        v
  React console (inbox / tomorrow list / job detail / predictive)
```

- **Backend**: Python, FastAPI, SQLite (SQLModel), one `llm.py` wrapper that speaks JSON schema and works with whichever key the team actually has. No framework roulette at 2am.
- **Frontend**: React plus Vite, Tailwind, MapLibre with an OpenStreetMap basemap (ODbL, credit shown). No Next.js, no auth, no build drama.
- **Jobs**: an in-process queue plus `asyncio`, not Celery. Redis is a distraction.
- **Adapters**: `channels/` for BlueBubbles, Twilio, and a web simulator, all behind one `Channel` interface. `works/` for the mock Confirm API and the CSV exporter, behind one `WorksSystem` interface. This is what makes the second-city and no-Mac stories true rather than rhetorical.

---

## 5. The AI, and the baselines that make it credible

Three steps, three baselines, three numbers on a slide. Build the baseline **first**, in the same afternoon, because it is 40 lines and it is worth a quarter of C2.

### 5.1 Triage: category, severity, duplicate

- **Baseline**: keyword and regex list over the transcript. Pothole words, fly-tip words, light words. Severity from a word list ("huge", "dangerous"). Duplicate by exact street string match.
- **Model**: vision plus text, forced to JSON with `category` (mapped to the Empro taxonomy), `severity` in {low, medium, high, emergency}, `confidence`, `evidence` (the phrase or region that drove it), `location_confirmed`.
- **Evaluation set**: 60 real Southampton reports pulled from FixMyStreet Open311, labelled by two of us in about 45 minutes, with a tie-break rule. Stratified on purpose: 15 pothole, 15 fly-tip, 15 street light and other, 15 deliberately ambiguous or multi-issue. Plus 20 real duplicate pairs and 20 hard non-duplicates harvested from the same streets.
- **Targets to state in the video**: category accuracy and macro-F1 against the keyword baseline, severity agreement against two human labellers, duplicate precision and recall. Quote the real numbers, including where the model loses.

### 5.2 Intake: the conversation

- **Baseline**: a fixed five question form, the thing the council has today.
- **Evaluation**: 10 scripted messy inputs (photo only, no punctuation, voice-note transcript, three issues at once, a location that is a pub name, a location outside Southampton). Measure completion rate, turns to complete, and whether the final record has location plus category plus photo.
- **The point**: the form gets a photo-only message and stops. The agent asks "where is this?" and carries on.

### 5.3 Predictive work: weather and tide

- **Baseline**: the fixed calendar. Mow every 21 days, sweep in November, clean gullies annually.
- **Model**: an inspection-priority score per asset from trailing rain, soil temperature and moisture, wind, leaf season, tide height and river discharge.
- **Honest framing**: we are not predicting grass height. We are ranking which assets to look at next, given spend. Report the trade-off curve: visits avoided at equal coverage, and the days it gets wrong.

### 5.4 The analysis that pays for itself

One cheap, real, testable finding from the FixMyStreet data, computed tonight:

> Blocked drain and gully reports in Southampton are N times more likely in the 48 hours after more than 10mm of rain, and they cluster on the streets that flood on a high tide.

That single correlation is the justification for the whole predictive module, it uses data we can definitely get, and it survives a judge's question because we can show the query. If the number turns out to be 1.3x, we report 1.3x and drop the module to a single screen. Do not fudge it.

---

## 6. Integration, stated honestly

The brief forbids using restricted council systems without prior agreement, so we cannot log into Confirm. What we do instead is more convincing than a fake login:

1. **A real interface contract.** `WorksSystem` with `create_work_order`, `assign_crew`, `get_capacity`, `update_status`, each with the fields a Confirm work order actually carries (asset id, defect code, location, priority, SLA due, crew, source, external ref).
2. **A working adapter against a mock Confirm API that we also ship**, so the call is real HTTP with real latency and real error paths, and the demo can show the request and response on screen.
3. **A CSV and XML export** shaped like a real works export, so a council can ingest it on day one without any integration at all. This is the "sell it next month" wedge.
4. **The honest sentence**: "Confirm has no public API. This is a 3 week adapter job against Causeway's data import, and we have built and tested the contract it plugs into." Judges reward that far more than a mocked screenshot.

The same pattern for the council's **Empro taxonomy**: mirror the service names from the live portal, map our categories to them, and keep the mapping in one file. That file is also the second-city story, because every council keeps its own copy and nothing else changes.

---

## 7. Data, with dates and licences

Every number on screen carries its source and its timestamp. `code/data/raw/MANIFEST.json` already records URL, UTC time, bytes and sha256, so the demo can say "collected 6 minutes ago" instead of "live" when it is not.

| Source | Use | Licence | Status |
|---|---|---|---|
| FixMyStreet Open311 | Real reports, photos, duplicates, the evaluation set | Open data, attribute mySociety and note the collection date | Verified working today; paginate slowly |
| Open-Meteo forecast and archive | Rain, wind, soil temperature and moisture, growth index | CC BY 4.0, attribute Open-Meteo | Verified, keyless |
| Open-Meteo marine | Tide height, wave height in Southampton Water | CC BY 4.0, **model output, not a gauge** | Verified, keyless |
| Open-Meteo flood | River discharge, Itchen and Test | CC BY 4.0 | Verified, keyless |
| EA flood-monitoring | Warnings, flood areas, stations | Open Government Licence v3 | Verified; empty on a dry day |
| postcodes.io | Geocoding and boundary | Free, OGL derived | Verified |
| Southampton council pages | Taxonomy, service codes, official links | Quoted and cited, not redistributed wholesale | Portal confirmed live |
| OpenStreetMap | Basemap | ODbL, credit required | Standard tiles |

Never present cached as live. Never present synthetic as real. The demo device's phone number is a burner, and the test conversations are labelled synthetic in the UI.

---

## 8. The demo, to the second

Stage 2 gives the panel their own input. Stage 1 gives the room a phone. Same 2 minutes both times.

The submission video is a trailer with a real product spine: AI b-roll for the world, continuous real screen capture for the workflow, about 1:46 of 2:40 real. That rule comes straight from the submission page, which says mock-ups or slides alone do not count as a demo, so the trailer can never carry the product on its own. Full beat sheet, shot list and edit settings are in `VIDEO.md`. Declared format: video 2:40 plus a 20 second live call to action.

| Time | Beat |
|---|---|
| 0:00 | Judge or volunteer types "there's a massive pothole outside the school on Weston Lane, nearly took my wheel off" with a photo |
| 0:10 | Agent: "Got it. Which school? I have Weston Lane but two entrances." One question, one answer |
| 0:25 | Agent: "Logged. Ref KB-1042. Priority urgent, Highways." Resident screen shows the reference |
| 0:35 | Console: the report lands, category pothole, severity high, confidence 0.91, with the evidence highlighted on the photo |
| 0:50 | Duplicate card: "also reported 4 times, 38m away, last one 2 days ago". Cluster merged, priority bumped. Say the number out loud |
| 1:05 | Agent has already raised WO-4471 in the works system. Show the request and 201 response. Crew assigned, tomorrow 08:00, batched with 3 jobs within 900m |
| 1:20 | Predictive pane: Thursday's tide is 4.9m with 18mm of rain on saturated ground, so 3 gullies on that route are pulled forward to today, in the same list. Timestamp on screen |
| 1:40 | Failure case one: a photo of a private car park. The agent does not guess. "That looks like private land, here is who to contact", and the report is marked for human review, not routed |
| 1:55 | Failure case two: the classifier hits a 6 second timeout, the keyword baseline still logs the report, the console says "degraded, human review". The job is never lost |
| 2:10 | Close the loop: officer presses Resolved, phone buzzes "the pothole on Weston Lane has been repaired" |

The two failure cases are deliberate. The judging page asks for at least one and rewards honesty; two, with different failure modes, is a stronger signal than a polished lie.

---

## 9. The BlueBubbles decision, and the ladder under it

**Gate at 16:00 today** (30 minutes, no more):

- Is there a Mac in the room with an Apple ID that can send iMessages? BlueBubbles needs macOS and a signed-in Messages app. If yes: install, set the server password, expose with Cloudflare tunnel or ngrok, point the webhook at our FastAPI, enable the Private API helper if the Mac allows it, send one test message to an iPhone.
- If no: **Twilio SMS sandbox**. Real phone channel, real webhook, ten minutes of setup, and it makes the architecture honestly channel-agnostic.
- If neither: the web simulator, which looks like Messages and is labelled as a simulator in the UI and in the video. Acceptable for development, not for the video, because the judges explicitly do not count mock-ups.

The pitch line is written to survive all three: **"the messaging layer is swappable, iMessage today, SMS already working, because a council cannot ask residents to install anything."** That is also true, and it is the actually important insight.

Two rules we keep even on a burner: only the message and the photo go to the model, never the handle or the number; and any real number that ever arrives during a demo is deleted the same day and we say so on the slide.

---

## 10. Four people, 22 hours

Roles are ownership, not isolation. Everyone touches the demo at the end.

| Who | Owns | Not their job |
|---|---|---|
| **A** | Channel plus intake agent. BlueBubbles or Twilio, webhook, session state, turn cap, resident comms, status lookups | The console |
| **B** | Triage. Vision, taxonomy mapping, severity, dedupe, priority score, and the entire evaluation harness with the baseline numbers | Scheduling |
| **C** | Console. Inbox, tomorrow list, job detail with audit trail, approve and override, predictive pane. The thing on screen | Model prompts |
| **D** | Works adapter, mock Confirm, CSV export, scheduler, predictive engine, data pipeline and manifest | Frontend polish |

### The schedule

| Window | Milestone | Gate |
|---|---|---|
| 15:15 to 16:00 | Scope freeze. Flat 25 word problem statement. Repo created, public, empty of secrets. BlueBubbles feasibility test | **Gate 1, 16:00: channel chosen, keys confirmed, repo live** |
| 16:00 to 19:30 | Skeleton end to end with a stub model: message in, row in SQLite, card in the console, work order in the mock. No AI yet | **Gate 2, 19:30: ugly but complete loop** |
| 19:30 to 01:00 | Real AI in. Intake agent, vision triage, dedupe, priority, resident replies. Data pull starts in the background | **Gate 3, 01:00: the rehearsed demo runs without hands** |
| 01:00 to 04:00 | Predictive engine, scheduler, adapter polish, analysis of drain reports against rain. Two of us sleep 04:00 to 08:00, two carry the polish | **Gate 4, 08:00: predictive pane has real numbers** |
| 08:00 to 10:30 | Evaluation numbers into the UI and the README. Failure cases made repeatable. Freeze features | **Gate 5, 10:30: feature freeze, no new ideas** |
| 10:30 to 12:00 | Video: capture the four real clips in one 40 minute block, assemble to the `VIDEO.md` beat sheet, upload unlisted. 150 word summary. README finished | **Gate 6, 12:00: video link in hand** |
| 12:00 to 12:45 | Submit everything, tick partner opt-in, verify the repo from a clean clone, demo rehearsal on the actual laptop | **Gate 7, 12:45: submitted, 15 minutes before the lock** |

Hard rules inside the schedule: nobody merges to `main` after 10:30. Nothing new is built after 10:30, only fixed. The video is recorded before the last hour, because the last hour is for submission and rehearsal.

---

## 11. What we cut, and why saying so helps

Cut list, stated on the trust slide because it is more credible than pretending:

- **Satellite imagery for grass cutting.** Sentinel-2 revisit is about 5 days, October is cloudy, and there is no ground truth for grass height. It would be a slide, not a demo, and the brief explicitly excludes a prediction that does not lead to a decision. We use soil temperature and moisture instead, and we say why.
- **Video understanding.** Accepted as an input, transcribed and first frame only, labelled as partial. Full video reasoning is a cost and latency trap in a live demo.
- **Real Confirm integration.** Restricted system, forbidden without agreement. Contract plus mock plus CSV instead.
- **Auth, multi-tenant, billing.** Not this weekend.
- **WhatsApp.** No time, and it needs Meta approval that will not arrive by Sunday.
- **Fine-tuning.** No.

---

## 12. The business case, with numbers you can say out loud

- **Cost per report**: one vision call plus one classification call, about £0.006 to £0.012. Hosting £60 a month. At 20,000 street reports a year, total running cost under £400.
- **Value per report**: 2.5 minutes of officer triage time at about £22 an hour loaded is roughly £0.90 of officer time, plus the avoided duplicate visit, which is the bigger number. A crew rolling to a duplicate pothole costs about £90.
- **Price**: £0.50 per report, or £25,000 a year uncapped, or £15,000 as a pilot on one service.
- **Payback**: about 830 officer hours a year, plus a plausible 8% cut in duplicate attended jobs on 6,000 jobs, is more than £40,000 of avoided cost. Say the assumption, do not hide it.
- **First three customers**: Southampton City Council street scene; Balfour Beatty under the Southampton Highways Partnership, who are paid against response times so a faster, cleaner queue is their incentive too; then a coastal authority on the same class of systems, Portsmouth or BCP, where the tide module is already built.
- **Second city**: change the taxonomy mapping file and the adapter, 2 to 4 weeks. The model does not change, the category list does.
- **What stops a big player**: FixMyStreet owns the report, not the work order. Causeway owns the work order, not the conversation. Nobody owns the join, and the join is the product.

---

## 13. Trust, in one slide

Minimal data by design: no name, no account, no address book access. The phone number is used to send a reply and is stored hashed, and it is never sent to a model. Photos and text only. Retention 30 days unless the job is open, deletion on request, and a one word "STOP" that works.

Human control: an autonomy dial from "suggest" to "execute", low confidence always to a human, and an override that always works and is always logged. The audit trail is append only, so a council can answer "why did the machine do that" in a complaint.

Safety: flood and road hazard guidance is a link to the Environment Agency and to 999, never our own words. Accessibility: works on any phone, voice notes accepted, plain English out, no app to install, no data plan beyond a text. And the honest limit, on screen: the tide figure is a model, the FixMyStreet sample is a sample, and ambiguous photos go to a person.

---

## 14. Risk register

| Risk | Chance | Response |
|---|---|---|
| No Mac, BlueBubbles impossible | High | Twilio SMS tonight, same interface. Channel-agnostic line in the pitch, which is true anyway |
| FixMyStreet rate limits dry up the eval set mid-build | Medium | Pull the 60 labelled reports first, cache to disk with the manifest, never rebuild the set |
| Open-Meteo overloaded (it answered "service overloaded" twice today) | Medium | Cache with timestamps, show the timestamp on screen, retry with backoff, fall back to the 14 day history already downloaded |
| Judged repo contaminated with pre-event code | Medium | New empty public repo for the entry, copy in only what is written after 20:00 Friday, state it in the README |
| The loop is not finished by 01:00 | Medium | Cut the predictive pane to one screen and the scheduler to earliest feasible slot. Never cut the resident reply, it is the demo |
| Team collapse at 04:00 | High | Sleep rotation, hard freeze at 10:30, one person owns submission and never codes after 11:30 |
| Video does not play or is over 3:00 | Medium | Record 2:40, upload at 12:00, play it back on the submission laptop before 12:45 |
| A judge asks "is this just FixMyStreet" | Certain | The answer is in section 16. Lead with the work order, not the report |

---

## 15. Questions we will be asked, and the answers

**"Isn't this FixMyStreet with extra steps?"** FixMyStreet ends where the report is sent. Our product starts there, and then does the eleven things an officer does afterwards, ending with a work order on a crew's list and a text to the resident. FixMyStreet is our data source, not our competitor.

**"Would a council let an AI create work orders?"** Not on day one. That is why the autonomy dial exists, and why every action is logged and reversible. Start in suggest mode, move to execute on the two categories where it is measured to be right.

**"What if the resident lies or sends a joke photo?"** Same as now: a human confirms. The difference is that geography, duplicates and ownership checks happen before anyone drives anywhere.

**"Why iMessage instead of a form?"** Because the form already exists and 755 fly-tipping cases sat open on a third party site. The barrier is not the form's design, it is opening it. Nobody installs an app for a pothole. Everyone can send a photo.

**"Is the AI doing the work or decorating it?"** Three measured steps against three baselines, numbers from real Southampton reports, and the failures shown. If the model were removed, the product would be a keyword filter that cannot read a photo.

**"What about people without an iPhone?"** SMS runs on the same pipeline today, and it is already working. Voice notes are accepted. That is the access answer, and it is a fair criticism of an iMessage-only product.

---

## 16. Between now and the lock

1. **Right now, 16:00**: decide the channel, create the public entry repo, confirm which model keys the team holds, and read this plan out loud once so nobody is surprised.
2. **Tonight**: ugly complete loop by 19:30. That is the only milestone that matters today.
3. **The two numbers to chase**: the triage baseline gap, and the drain-report rain correlation. Everything else is polish.
4. **Submit at 12:45**, not 12:59. The organiser's wording is that an incomplete submission is not shown in Stage 1 at all, which is a zero, not a low score.

Nothing here needs a slide.

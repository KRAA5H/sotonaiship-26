# Kerbside: the plan (v2, final)

**This document is the single source of truth. If it is not in here, it is not in the build.**
Written Sat 17 Oct 2026, 16:40. Submission locks Sun 18 Oct 13:00. About 20 hours.

It supersedes v1 and it supersedes `CRITIQUE-vs-GOMER.md` wherever the two disagree. The argument behind each decision is in `DECISIONS.md`. Do not re-litigate a decision without adding a line to that file.

Working name: **Kerbside**.

---

## 1. The idea on one page

**Pitch, one sentence.** We help Southampton City Council's street-scene and coastal teams turn residents' messages into deduplicated, prioritised work orders on tomorrow's jobs list, using AI that runs every step from the first text to the crew's schedule.

**The user.** The primary user is the resident who currently falls out of the council's report portal: the one with a photo and no words, the one who does not know which of the council's 60 services handles a blocked drain, the one who gave up after reporting the same pothole twice. The operational beneficiary is the street-scene officer, and the buyer is the council.

**Why now, in their numbers.** 10,948 fly-tipping incidents in the year to March 2024, the highest in Hampshire. A rate rising 37.6 to 42.7 to 47.1 per 1,000 across three recorded years. 61% on council-owned land. £830,000 already allocated to dedicated pothole crews. 755 fly-tipping cases still open on FixMyStreet for Southampton as of February 2025. The council is spending real money on the symptom and answering residents one email at a time.

**What we do that nobody else in the room does.** Everyone stops at "routes it to the right team". We finish the chain: the work order is created in the works system, the crew and kit are assigned, the job is batched into a route, the resident is told when it will be done and told again when it is done, and the same list also carries work the council did not know it needed yet because the weather and the tide say so.

**The five numbers we will be judged on**, all in `NUMBERS.md` with a source and a date:

1. Category accuracy against the keyword baseline, on 60 real Southampton reports.
2. Duplicate catch rate against 20 known duplicate pairs.
3. Interactions to report a pothole, ours versus the council's own portal.
4. Cost per report, including inference.
5. Officer minutes saved per 100 reports.

**What we deliberately do not do.** No app, no account, no name. No replacement of Confirm or Empro. No satellite imagery. No general chatbot about Southampton. No claim to reduce fly-tipping or congestion.

---

## 2. Scope, frozen at 17:00 today

Anything not on the "in" list is out. Additions require a line in `DECISIONS.md` and a named person giving up something else.

### In

| # | Thing | Owner |
|---|---|---|
| 1 | iMessage intake via BlueBubbles, plus SMS and a simulator behind one interface | A |
| 2 | One-shot-first intake agent, confirm-back, plain English, 2 question cap | A |
| 3 | Triage: category, severity, confidence, evidence | B |
| 4 | Dedupe: 80 metres, 14 days, cluster count | B |
| 5 | Priority with three visible factors | B |
| 6 | Ownership resolver, tier-aware (function x location) | B |
| 7 | Mock works system, work order creation, CSV export | D |
| 8 | Scheduler: tomorrow list, geo batched, SLA aware | D |
| 9 | Officer console: inbox, today list, job detail, audit trail, reply, override | C |
| 10 | Resident loop: acknowledgement, status lookup, completion text, escalation | A |
| 11 | Predictive pane: rain, tide, growth, leaf | D |
| 12 | Evaluation harness and the baseline | B |
| 13 | The seven beat demo, working end to end | all |

### Out

Auth, billing, multi-tenant, real Confirm access, WhatsApp, video understanding, fine-tuning, satellite imagery, a public map, consultation analysis, full council-service explainers.

### Stretch, only if the loop is green by 01:00

Event-driven demand (fixtures, cruise calls, festivals) and the tier resolver demo case. Nothing else.

---

## 3. The product

### 3.1 The resident

1. Texts a photo, or a photo and a sentence, or just a sentence.
2. **One-shot by default.** If the message has enough to work with, the reply is one line and a reference. No questions at all.
3. **Confirm-back, not interrogation.** If something is genuinely ambiguous, the agent reads it back in the resident's own words and asks yes or no. One tap to answer.
4. **At most one clarifying question**, and only when the report cannot be actioned without it. Never two.
5. The reply always says what happens next, who owns it, and when to expect it. Plain English, reading age 9 to 11, no jargon, no service names, no internal codes except the reference.
6. Later, unsolicited: "the hole in the road on Weston Lane has been repaired". Or, if rejected, why, and who does own it.
7. "status KB-1042" returns the current state at any time.
8. "not fixed" or "I disagree" routes to the council's formal complaints process and the ward councillor, with the official link.

Voice notes are accepted and transcribed. Nothing requires the resident to install anything, create an account, or remember a password.

### 3.2 The officer

One console, four panes.

- **Inbox**: live reports, category, severity, confidence, and the evidence that drove it.
- **Tomorrow list**: capacity aware, batched by geography, SLA due times, weather and tide flags. This is the artefact a crew reads.
- **Job detail**: the resident's own words and photo, the cluster ("4 reports, 38m, 2 days"), the asset, the audit trail, **Approve**, **Override** with a reason that becomes a labelled example, and **Send update**. Send update is one-way: the officer sends a status message ("crew coming Thursday"), the resident receives it, and any answer the resident sends is read by the agent and folded back into the report. There is no human-to-human chat, and no inbox for conversations.
- **Predictive**: ranked work no resident reported, with the source and timestamp of every input, writing into the same Tomorrow list.

### 3.3 The agentic chain

The agent runs every step. A human appears in two places only: to approve the first N work orders until the error rate is measured, and to override anything at any time. The autonomy dial exists as a safety feature for a cautious council, not as the headline. Lead with what the system executes.

| # | Step | What the agent does | Fallback |
|---|---|---|---|
| 1 | Intake | Reads text, photo and metadata; decides complete, confirm, ask or decline | Declines to guess |
| 2 | Evidence | Defect type, severity cues, hazard cues, from the image and the words | Low confidence goes to human review |
| 3 | Locate | Postcode or landmark to lat/long, boundary check | Outside area, names the right authority |
| 4 | Ownership | Function x location to (authority, team): SCC, Hampshire County, Eastleigh, parish, National Highways, EA, private | Says a human will confirm, gives the likely owner |
| 5 | Dedupe | 80m and 14 days, same category or embedding, merge into a cluster | Borderline keeps both and links them |
| 6 | Classify | Maps to the council's taxonomy in `taxonomy.json` | `other`, never a silent guess |
| 7 | Priority | severity x exposure x report factor, all three shown | Score is never a black box |
| 8 | Work order | Creates it in the works system: asset, defect, location, priority, SLA, crew, source | Queue and CSV export, stated on screen |
| 9 | Schedule | Batches nearby jobs, respects SLA and capacity, re-optimises on an urgent arrival | Earliest feasible slot |
| 10 | Resident comms | Acknowledge, expectation, completion, rejection with reason, escalation route | SMS fallback |
| 11 | Audit | Every step: input, output, model, latency, confidence, override | Job is not created if the log fails |

---

## 4. Contracts, frozen. This is what lets four people work at once.

Nobody invents a field, a status, an endpoint or a category. If something is missing, add it to `DECISIONS.md` and A merges it.

### 4.1 Vocabulary

| Thing | Values |
|---|---|
| Category (enum) | `pothole`, `road_defect`, `dumped_rubbish`, `street_light`, `drain_flooding`, `pavement`, `graffiti`, `tree`, `other` |
| Severity | `low`, `medium`, `high`, `emergency` |
| Status | `received`, `needs_info`, `triaged`, `scheduled`, `in_progress`, `resolved`, `rejected`, `referred` |
| Report id | `KB-` plus 4 hex, e.g. `KB-1042` |
| Work order id | `WO-` plus 4 digits |
| Cluster id | `C-` plus 4 digits |
| Timestamps | ISO 8601 UTC, always |

`taxonomy.json` is the only place that maps enum to plain English to the council's Empro service name. The console fetches it from `/taxonomy`; it never hardcodes labels.

### 4.2 The report object

This is the only object that crosses a module boundary. Anything not here is internal.

```json
{
  "id": "KB-1042",
  "created_at": "2026-10-17T17:02:11Z",
  "channel": "imessage",
  "sender_hash": "9f2c...",
  "raw_text": "massive pothole outside the school nearly took my wheel off",
  "has_photo": true,
  "photo_path": "data/attachments/9f2c-1.jpg",
  "category": "pothole",
  "category_display": "a hole in the road",
  "severity": "high",
  "confidence": 0.91,
  "evidence": "deep crater, kerb line visible, no white paint marking",
  "description": "Deep pothole outside the school on Weston Lane",
  "location_text": "Weston Lane",
  "lat": 50.9025,
  "lon": -1.4044,
  "in_area": true,
  "owner": {"authority": "Southampton City Council", "team": "Highways", "reason": "adopted highway inside the city boundary"},
  "cluster_id": "C-0007",
  "reports_in_cluster": 4,
  "priority": 9.6,
  "priority_factors": {"severity": 3, "exposure": 2, "report_factor": 1.6},
  "status": "scheduled",
  "work_order_id": "WO-4471",
  "official_link": null,
  "audit": [{"at": "2026-10-17T17:02:12Z", "actor": "agent", "action": "classified", "detail": "pothole, high, 0.91"}]
}
```

### 4.3 Endpoints

| Method | Path | Body / query | Returns |
|---|---|---|---|
| POST | `/webhook/bluebubbles` | BlueBubbles payload | `{ok, action, reply}` always 200 |
| POST | `/simulate` | `{sender?, text?, photo_path?}` | `{ok, action, reply, report_id}` |
| GET | `/reports` | `?status=&limit=&since=` | list of report summaries |
| GET | `/reports/{id}` | | full report object |
| POST | `/reports/{id}/status` | `{status, note, actor}` | updated report, resident texted |
| POST | `/reports/{id}/notify` | `{text, officer}` | one-way update sent to the resident |
| GET | `/workorders` | `?date=` | tomorrow list |
| GET | `/taxonomy` | | enum, display, empro name |
| GET | `/health` | | mode, model, counts, version |

### 4.4 Database tables

`reports`, `sessions`, `work_orders`, `events` (append only audit), `attachments`. One `schema.sql`, `IF NOT EXISTS`, run at startup. No phone number in `reports`. A salted hash identifies the sender; the chat id lives in `sessions` only so a reply can be delivered, and has a delete path.

### 4.5 Interfaces

```python
class Channel:            # channels.py
    def send(self, chat_guid: str, text: str) -> bool
    def fetch_attachment(self, guid: str) -> str | None
    def normalise(self, payload: dict) -> Inbound | None

class WorksSystem:        # works.py
    def create(self, report: dict) -> dict      # {"work_order_id", "crew", "slot"}
    def set_status(self, wo_id: str, status: str) -> None
    def capacity(self, date: str) -> dict

class Brain:              # llm.py
    def decide(self, system: str, messages: list, image_path: str | None) -> dict
```

`llm.py` must work with **no API key** by falling back to a deterministic stub, because the stub is also our C2 baseline. Every response carries `mode: "model" | "stub"` and the console shows it. Never present stub output as AI output.

---

## 5. Who does what, and how we merge

| Person | Owns these files, and only these | First deliverable |
|---|---|---|
| **A** | `code/app.py`, `code/channels.py`, `code/intake.py`, `code/llm.py`, `code/schema.sql`, `code/.env.example` | The webhook running and replying, with the stub brain |
| **B** | `code/triage.py`, `code/taxonomy.json`, `code/eval/**`, `NUMBERS.md` | Triage plus the baseline and the labelled set |
| **C** | `code/web/**` | Inbox and job detail reading from `/reports` |
| **D** | `code/works.py`, `code/predict.py`, `code/data/**` | Mock works system and the tomorrow list |

**Rules.**

1. `main` is always runnable. `python code/smoke.py` must pass before any merge.
2. Branch per person. Merge only at a gate, or when a dependency is blocking someone.
3. Never edit a file you do not own. Need a change in someone else's file? Write it in `DECISIONS.md` and message them.
4. Contract changes need one line in `DECISIONS.md`, signed with a name.
5. One home for code: `code/`. The duplicate `.py` files at the repo root are frozen and get deleted before the judged repo exists. Do not edit them.
6. Every number quoted in the pitch, the video or the README comes from `NUMBERS.md`. No ad hoc numbers.
7. Five minute standup at each gate. One sentence each: done, next, blocked.

---

## 6. Schedule and gates, re-baselined at 16:40

| Window | What has to be true | Gate |
|---|---|---|
| 16:40 to 18:00 | Contracts agreed, repo tidy, channel decision made, stub brain answering `/simulate`, console showing one report | **G1 18:00: a message becomes a row and a card** |
| 18:00 to 21:00 | Real model in, triage, dedupe, work order, priority, tomorrow list | **G2 21:00: the seven beats run without hands** |
| 21:00 to 02:00 | Resident loop, officer reply, escalation, eval set labelled, scheduler, predictive pane | **G3 02:00: demo repeatable three times in a row** |
| 02:00 to 04:00 | Resilience, failure cases, tier resolver, video capture rig tested, two people sleep | **G4 04:00: everything on the demo path works or is cut** |
| 08:00 to 10:30 | Numbers into the UI and README, readability pass, freeze | **G5 10:30: feature freeze** |
| 10:30 to 12:00 | Video captured and uploaded, summary written, README complete | **G6 12:00: link in hand** |
| 12:00 to 12:45 | Submit, verify clean clone, rehearse on the laptop | **G7 12:45: submitted** |

Nothing new after 10:30. Only copy and fixes.

---

## 7. The demo, frozen. Seven beats, in this order.

This is what every module is optimised for. If a feature does not appear in these seven beats, it does not exist.

| Beat | What the room sees | Proven by |
|---|---|---|
| 1 | A photo with no words at all, and one line back with a reference | A |
| 2 | A vague message, one confirm-back, then the reference | A |
| 3 | The report landing on the officer's card with the photo evidence and the confidence | C |
| 4 | The duplicate cluster: 4 reports, 38m, 2 days, priority bumped | B |
| 5 | The work order created, crew and tomorrow 08:00, batched with 3 nearby jobs | D |
| 6 | The predictive pane: Thursday's 4.9m tide and 18mm of rain pull 3 gullies forward to today | D |
| 7 | The officer presses Resolved, the resident gets the completion text | A, C |

**Failure cases, both shown, both rehearsed.**

- A report from outside Southampton: the agent names the right authority instead of accepting it.
- The model times out: the stub logs the report, the console says degraded, nothing is lost.

---

## 8. Data, with dates and licences

Every number on screen carries a source and a timestamp. `code/data/raw/MANIFEST.json` records URL, UTC time, bytes and sha256.

| Source | Use | Licence | Verified |
|---|---|---|---|
| FixMyStreet Open311 | Real reports, photos, duplicates, the labelled set | Open, attribute mySociety, record the date | 17 Oct, 200 with a 1000 cap and rate limits |
| Open-Meteo forecast and archive | Rain, wind, soil temperature and moisture, growth index | CC BY 4.0 | 17 Oct, keyless |
| Open-Meteo marine | Tide and wave height | CC BY 4.0, **model output not a gauge**, say so | 17 Oct, keyless |
| Open-Meteo flood | River discharge, Itchen and Test | CC BY 4.0 | 17 Oct, keyless |
| EA flood-monitoring | Warnings, areas, stations | OGL v3 | 17 Oct, empty on a dry day, that is the missing-data case |
| postcodes.io | Geocoding | Free, OGL derived | 17 Oct |
| Southampton portal | Taxonomy, official links | Quoted and cited | Portal live, Empro |
| OpenStreetMap | Basemap, ODbL credit | ODbL | standard |

Never present cached as live, or synthetic as real. The test device number is a burner, and the video says so.

---

## 9. Evaluation, and the numbers we will quote

B owns this. The labelled set is built first, because it is the thing everyone else's claims rest on.

- **60 real Southampton reports**, labelled by two people with a tie-break rule. 15 pothole, 15 dumped rubbish, 15 street light and other, 15 deliberately ambiguous or multi-issue.
- **20 real duplicate pairs and 20 hard non-duplicates**, harvested from the same streets.
- **Baselines**: keyword and regex list for triage; fixed five-question form for intake; fixed calendar for predictive.
- **Deliverable**: one table in `NUMBERS.md` with model versus baseline, per case, including the losses.
- **Live robustness**: five random unseen FixMyStreet reports per hour, run through `/simulate`, to make sure the panel's own input cannot break it.

---

## 10. Business case

- **Cost**: about £0.006 to £0.012 per report in inference, £60 a month hosting, under £400 a year at 20,000 reports.
- **Value**: 2.5 officer minutes per report at about £22 an hour loaded, plus the avoided duplicate visit, roughly £90 a crew roll.
- **Price**: £0.50 per report, or £25,000 a year uncapped, or £15,000 for a one-service pilot.
- **Payback**: about 830 officer hours a year plus an 8% cut in duplicate attended jobs. State the assumption.
- **First three customers**: Southampton City Council street scene; Balfour Beatty under the Southampton Highways Partnership, paid against response times; then a coastal authority on the same systems, Portsmouth or BCP.
- **Second city**: taxonomy mapping file plus the ownership resolver. Two to four weeks. The model does not change.
- **The moat**: FixMyStreet owns the report, Causeway owns the work order, nobody owns the join. The join is the product.

---

## 11. Trust

No name, no account, no address book. A salted hash identifies the sender; the number is never sent to a model. Photo and text only. Thirty day retention, deletion on request, STOP works. Every agent action is logged and reversible. Low confidence always goes to a human. Safety and flood guidance is a link to the Environment Agency or 999, never our own words. Accessibility: any phone, voice notes, plain English, no install, freephone number in the real deployment. Named service manager accountable, and every decision exported as one readable paragraph so a councillor can answer for it.

---

## 12. Risks

| Risk | Response |
|---|---|
| No Mac for BlueBubbles | Twilio SMS tonight behind the same `Channel` interface; simulator for development. Channel-agnostic is true anyway |
| Model key missing or rate limited | Stub brain keeps the loop alive; the console labels it |
| Open311 rate limits | Cache the 60 labelled reports first, never rebuild the set |
| Open-Meteo overloaded | Cache with timestamps, retry with backoff |
| Loop not green by 21:00 | Cut the predictive pane, keep all seven beats |
| Merge conflict at 2am | Ownership rules above, `main` always runnable |
| Video too long | 2:40 plus a 20 second live call to action, declared at submission |
| Team collapse | Sleep rotation, freeze at 10:30, one person owns submission and stops coding at 11:30 |

---

## 13. Submission checklist

- [ ] Seven beats work live, three times in a row
- [ ] Two failure cases demonstrated
- [ ] `NUMBERS.md` complete, every number sourced and dated
- [ ] Public judged repo, created after hacking opened, no duplicate root files
- [ ] README: setup, data with dates and licences, what the AI does, what was AI-generated, test results, known limits
- [ ] One command to run, tested from a clean clone
- [ ] No keys or secrets in the repo, `.env.example` blank
- [ ] Synthetic data labelled synthetic in the UI
- [ ] Safety guidance links to an official source
- [ ] Video 1:00 to 3:00, shows the real product, uploaded unlisted by 12:00
- [ ] 150 word summary
- [ ] Format declared: video 2:40 plus 20 second live call to action
- [ ] Partner opt-in ticked if wanted
- [ ] Everyone on the team page

---

## 14. The four answers to rehearse

**"Isn't this FixMyStreet with extra steps?"** FixMyStreet ends when the report is sent. We start there and finish the eleven things an officer then does, ending with a work order on a crew's list and a text to the resident. They are our data source, not our competitor.

**"Why a chat interface when councils have rejected chatbots?"** This is not a chat about the council. It is a photo, one line back and a reference, with at most one question when the message is unusable. It exists for the residents who cannot get through the portal at all, and the existing channels all stay.

**"Is there a human on the other side?"** No. The counterpart is the model, and it answers in seconds at 3am, which is the point. A human enters in two places: to approve the first few work orders until the error rate is measured, and whenever the resident asks for a person or disagrees, which routes to the council's complaints process and their ward councillor. We are not building a messaging service and there is no human DM channel to staff.

**"Who is accountable when it books a crew to the wrong place?"** A named service manager, a suggest-only mode that can be switched on, and an append-only audit a councillor can read in one paragraph. The machine never spends public money without approval until its error rate on that category is measured.

**"Does the AI really do all of that?"** Yes, all eleven steps, and the demo shows each one. Where it cannot, it says so and hands to a human, which is also in the demo.

# Decisions

The short record of what we decided and what we rejected, so nobody re-opens a settled question at 2am.

**Rules.** Every contract change, scope change or feature removal gets one line here. One line each: what, why, who. `PLAN.md` is the source of truth; this file explains how it got that way.

---

## The identity decisions

| # | Decision | Why | Decided by |
|---|---|---|---|
| D1 | The problem statement stays **volume and money**: 10,948 incidents, the rising rate, 755 open cases, £830,000 on potholes | It is the strongest evidence in the brief, it is local, and a public audience feels it immediately. The "asymmetric information" reframe is a supporting line, not the headline | Team |
| D2 | The pitch leads with **the agent executing every step**. We do not open with "one human decision, ten machine steps" | That is the ambition, and it is what the demo shows. The autonomy dial and the approvals stay as safety features, described when asked, not as the headline | Team |
| D3 | **One-shot first.** Photo and words in, one line and a reference out. Zero questions when the message is complete, one confirm-back when it is ambiguous, never a second form | It answers the "not another chatbot" objection structurally, and it makes the demo faster | Team |
| D4 | The **primary user is the resident who falls out of the portal**, the officer is the operational beneficiary, the council is the buyer | It gives C1 a named user with a measurable inclusion claim, and it uses the one case where conversational intake is clearly justified | Team |
| D5 | **The only counterpart is the model.** No human-to-human chat, no shared inbox for conversations, no DM product. An officer can send a **one-way status update**, and anything the resident sends back is read by the agent | We are not building a messaging service. Staffing a human chat is out of scope and it is not the product. Escalation to the complaints process covers the case where a person is genuinely needed | Team |

## What we kept from the Gomer review

| # | Decision | Why |
|---|---|---|
| D6 | **Neighbour count** on the acknowledgement and the officer card ("3 other people nearby reported this") | Cheap, and it turns a private report into visible collective action without exposing anyone's data |
| D7 | **Escalation route**: "not fixed" or "I disagree" routes to the council's formal complaints process and the ward councillor, with official links | The machine must never be a wall. This is two hours of work and it protects the weakest moment in the product |
| D8 | **Tier-aware ownership resolver**: function x location to (authority, team) | In Hampshire the same defect belongs to county, district or parish depending on the function. A single routing table would be wrong one mile outside the city, and it is also our best failure case |
| D9 | **Plain English** everywhere resident-facing: "hole in the road", not pothole. Reading age 9 to 11, measured | It is the inclusion claim made real, and it takes an afternoon |
| D10 | **Photo-only opening** in the video | It proves the inclusion claim in seven seconds, better than any statistic |

## What we rejected

| # | Rejected | Why |
|---|---|---|
| D11 | Reframing the problem statement around "the council cannot see the problem" | The council can see it. The volume and cost evidence is stronger and less arguable |
| D12 | "One human decision, ten machine steps" as the headline | Honest, but it under-sells what the system does and it is not what the judges are asking about |
| D13 | Officer free-text chat with the resident | Out of scope, needs staffing, and it turns the product into a messaging service |
| D14 | Consultation comment analysis | Good second product, different user, different week. Roadmap only |
| D15 | Satellite imagery | Five day revisit, October cloud, no ground truth. Cannot be demonstrated live |
| D16 | Building an auth system, billing, or multi-tenancy | Not this weekend |

## Engineering decisions

| # | Decision | Why |
|---|---|---|
| D17 | **One home for code: `code/`.** The duplicate `.py` files at the repo root are frozen, and are deleted before the judged repo is created | Two copies of the truth is the fastest way to lose an hour. Do not edit the root copies |
| D18 | **The brain must run with no API key**, falling back to a deterministic stub, and every response says whether it came from the model or the stub | Unblocks everyone tonight, and the stub is also our C2 baseline. Never present stub output as AI output |
| D19 | **Contracts are frozen**: vocabulary, report JSON, endpoints, tables, interfaces, as written in `PLAN.md` section 4 | Four people cannot merge against moving shapes |
| D20 | **`main` is always runnable**, `python code/smoke.py` passes before any merge | Demo risk is the biggest risk we have |
| D21 | **Every quoted number comes from `NUMBERS.md`** | The video, the pitch and the README must not drift apart |
| D22 | Video is a **trailer with a real product spine**, 2:40 plus a 20 second live call to action, declared at submission | The submission page requires real product footage, so the trailer can never carry it alone |
| D23 | Model access is **OpenAI-compatible over HTTP**, not the Anthropic SDK. `LLM_BASE_URL=https://openrouter.ai/api/v1`, `LLM_MODEL=nvidia/nemotron-3-super-120b-a12b:free` | Keys are unsettled. The `openrouter/free` router returned "User Safety: safe" instead of an answer, so a specific free model is pinned. It answered correctly in 3.8 to 8.0 seconds. Swapping provider is two env vars |
| D24 | BlueBubbles sends with `method=apple-script` | `private_api` is false on server 1.9.9, so `private-api` would fail every send |
| D25 | Plans stay short and the todo list carries **only live development work** | A plan nobody reads is worse than no plan |
| D26 | **Reports follow `CLAUDE.md` and `dashboard/schema.sql`, replacing `PLAN.md` section 4.** One 11-column `reports` table, `R-0001` ids, statuses `new` / `in_review` / `resolved`, no coordinates, no channel, residents see only `/r/<link_token>`. Duplicates: same category, same location text, open (not resolved), within 30 days, as in `agent/categories.json`. The KB-xxxx report object, its statuses and the 80 m / 14 day rule are retired | The newer design is what the dashboard, the fake data and the agent tools are built on; two report shapes would split the team. Signed: Aadil |
| D44 | **Text calls have thinking disabled; image calls keep it.** DeepSeek ignores effort none and enabled false, but `thinking: {type: disabled}` removes reasoning. Images must keep `reasoning: low` or the reply comes back empty | The owner asked for non-image messages to stop thinking. Verified against the API: 3 to 4 output tokens instead of 64 to 170 |
| D45 | **The triage agent is the orchestrator of a multi-agent workflow** (`code/agents/`, per `plans/agents.md`). It calls safety, location, photo (in parallel), category, duplicate, records and reply in order; the channel only delivers. Only triage, photo and reply call a model | Owner's call: one agent owns the turn, and the plan's agents become real modules with their own tests, without separate services. Signed: Aadil |
| D46 | **DeepSeek with thinking off for every call**, images included. Supersedes D44 for images: an image goes with thinking off first, and only an EMPTY reply is retried once with low thinking, logged so its rate can be counted | Thinking costs seconds a resident on a phone can feel. Every call now logs tokens and latency (never text) to `code/logs/llm_usage.jsonl`, so cost per report can be measured. Signed: Aadil |
| D47 | **Location is checked against Southampton City Council's real boundary and an offline list of every street** (OpenStreetMap, ODbL), not a postcode prefix. The map page is served on the bot's own address, with a street drop-down filtered on the phone and "use my current location" | Some SO postcodes are Eastleigh or Totton. A typed street is matched in under a millisecond with no model call, which fixes the follow-up bugs (TODO 1.2, 1.3). Nominatim forbids search-as-you-type, so the drop-down never calls it. Signed: Aadil |
| D48 | **Neighbour noise, nuisance and property concerns go to the council's own form; nothing is saved** | From `plans/agents.md`: a pin there would log someone's home. Signed: Aadil |
| D49 | **Each category keeps its own duplicate window** (fly-tipping 7 days, pothole 30, graffiti 14, litter 3, missed bin 7) and a missing location never matches | From `plans/agents.md`; the missing-location rule fixes TODO 1.4. Signed: Aadil |
| D50 | **`is_report` governs capture; the category's outcome governs only what we say next.** A real report the model maps to `info_only` or to an unknown id is saved as `unclear_other` and the reply says it has not gone to the council. `outside_southampton`, `not_council_trunk_road`, `not_council_utility`, emergency and the D48 handoffs still save nothing. Supersedes D28's blanket refusal for this case | The reported fallen-tree conversation: the model said `is_report: true`, then `triage.normalise` discarded it because flooding is `info_only`, so no row existed and the correction had nothing to attach to. Reproduced offline, then fixed | Owner instruction, 2026-10-18 |
| D58 | **`save_report` no longer decides whether an outcome is worth keeping.** It requires a known category and a description, accepts a missing street as `Not given`, and refuses only the explicit `NEVER_SAVED` set. The capture policy lives in `triage.normalise` and, later, in the graph | The old gate refused anything without a location or without a `council_report` outcome, which is the same failure one layer down. The transaction, the token and the duplicate re-check are unchanged | Owner instruction, 2026-10-18 |
| D59 | **The resident reply is the template. The model is off the send path.** `voice.say` returns the template unchanged; `voice.generate` and `voice.lint` stay for the graph writer, which will be handed an executed outcome. The council-review claims in `logged`, `located` and `already_yours` are removed | Rephrasing the intended plan is what made a wrong decision sound confident. Template-only is a deliberate, temporary loss of naturalness until the writer lands | Owner instruction, 2026-10-18 |
| D60 | **Playbooks first, subagents on evidence.** A category group starts on deterministic handling. It is promoted to a specialist subgraph only when a measured trigger fires: more than 30% `uncertain`, more than 10% `mismatch` or category change, a repeated missing-requirement question, more than 20% officer edits, or an unsupported claim. The playbook stays the requirements and fact source, the subgraph must beat it on the trajectory slice, and at most two promotions happen before the freeze | Owner instruction: if the playbooks do not carry a group, give that group a subagent. This keeps the cheap path cheap and stops a specialist being added because it sounds impressive | Owner instruction, 2026-10-18 |
| D51 | **Add `capture_state` and `routing_status` to `reports` as additive columns**, keeping `status` as `new`/`in_review`/`resolved`. `capture_state` is captured, locally_actionable, submission_ready or submitted. `routing_status` is needs_review or verified. The incident draft and its version live in `threads.incident_draft`, not in `reports` | The four readiness states are the honest way to separate capture from routing, and the review flag is what protects an unclear capture. One writer for the policy fields: `set_policy_fields` in `code/graph/schemas.py` | Owner instruction, 2026-10-18 |
| D57 | **Keep the data and capability layer.** `agent/`, `code/geo/`, `code/data/`, `code/eval/`, `dashboard/`, `code/web/` and the tested agent services stay. The rebuild is the decision and runtime layer only. Retire only the dead second paths, the old orchestration, the static prototype and the duplicate zip | Rewriting verified facts, geography, schema and transport would add risk without changing the failure | Owner instruction, 2026-10-18 |
| D55 | **The resident page and the reply brief stop claiming council review or resolution.** A local save says it is saved here and has not gone to the council; `website.STEPS`, `tools.STATUS_TEXT`, `resident.html`, the greeting and the photo ask match that. `messages` no longer asserts trunk-road ownership | The page contradicted the text message the resident had just received. `status` is a local column flipped on our dashboard; it is not evidence of council action | Owner instruction, 2026-10-18 |
| D53 | **The LangGraph runtime replaces `TriageAgent` as the decision layer from Step 6.** D45's "modules, not subgraphs" is superseded for the decision layer; the channel and the tools remain modules. `MODE=legacy` keeps the old path until the trajectory suite passes | The graph owns hydration, precheck, capture and later decide/validate/execute. Keeping the old orchestrator as the decision layer would leave the failure in place | Owner instruction, 2026-10-18 |
| D56 | **No chat handle is persisted.** Threads are keyed by the salted `reporter_ref`. The outbox stores `thread_id`; the channel resolves the chat before sending. An unsent row after a restart is marked `undeliverable` and surfaced on `/council` | Storing a BlueBubbles chat guid would store the phone number. A queued message is not a delivered message, and a restart must not guess a destination | Owner instruction, 2026-10-18 |
| D42 | **A link is sent as its own message, about a second after the words.** `deliver()` splits the body from the link and sends them separately | A wall of text with a URL at the end reads like a form. A person texts the answer, then the link. Tested live: body, then link |
| D43 | **A shared pin is a location source.** Apple or Google map links are parsed for lat,lon, reverse geocoded to a street and area, and fill a missing report location instead of asking. A pin with no words asks for the problem and keeps the place | The backend existed but was never reachable from the iMessage flow, so a pin got "I could not read that". The pin is the easiest way for a resident to say where |
| D40 | **One turn per sender at a time.** A message that arrives while a turn is running is queued and handled after it, never in parallel. The burst timer only starts when the sender is idle | Two concurrent turns could save the same report twice and ask a question the resident had just answered. Found by an independent code audit |
| D41 | **The failure reply never claims a report was logged.** If handling throws, the resident gets a neutral apology, not "that is logged" | The old stub promised a crew and a log that did not exist. A false claim is worse than an apology |
| D38 | **Bursts are coalesced, not answered one by one.** A per-sender 2.5 second quiet window, and messages that arrive while we are generating are folded into the same turn before anything is saved | Residents type in bursts. Answering the first fragment is the fastest way to look deaf, and a second reply to the second fragment doubles the noise. 2.5s is the common range (OpenClaw defaults 2s, WhatsApp 5s) |
| D39 | **Never lead with what we do not know.** "Not sure", "no checked answer" and "honestly" are banned in code, and the council page is a fallback at the end, never the opening. The first move is always a question or an offer to log | The owner's judgement: an immediate redirect to the council form makes the product useless. The reply must keep the resident with us first |
| D35 | **Resident replies are written by the model from a brief, then linted, with the old templates as the fallback.** The model never sees the link and never writes a URL. Required strings (spoken category, street, status, org, contact) and required meaning phrases are checked on every reply | A fixed template reads automated, and the owner judged that the biggest product weakness. The lint keeps the safety of a template while the words stay human. Cost of one extra call per reply is accepted |
| D36 | **The register is a friendly young council employee**: casual, contractions, helpful, no corporate phrasing and no slang that dates. The examples in `code/voice.py` are the contract | The owner's instruction, in his words: it should feel like texting a person who works there |
| D37 | **Photos stay in BlueBubbles and the database stores a reference.** `photo_guid` and `photo_mime` are additive columns, migrated in `init_db`. `GET /r/<token>/photo` is token-only, no-store, no-referrer, and the guid never appears in a URL. This is a contract change for `code/reports_db.py`, which Section 3 owns, agreed so photos can appear on cards later without storing bytes in SQL | The owner chose file references over storing images in SQL. A guid is re-fetchable and the raw bytes never enter the repo or the database |
| D31 | **Grounded answers use the full fact sheet, not a vector database and not keyword retrieval.** All 53 dated facts fit in one prompt (about 2,940 tokens). The model returns the fact numbers it used, and we append the citation. It answered 12 of 12 evaluation questions correctly and refused 2 of 2 unanswerable ones | A keyword list failed on natural language ("gas leak" matched nothing) and was hand-maintained. An embedding model would mean a second provider and key for no measurable gain on 50 documents. Trigger to revisit: if answer citation accuracy falls below 10 of 12 |
| D32 | **Act first, ask second.** A council report with no street is saved with location "Not given", and the resident's next short message fills that row in rather than creating a second report | A missing location used to throw the report away. An incomplete card is the truthful state and the officer can see it |
| D33 | **One module owns every resident-facing string**, with the copy rules enforced as tests: three lines, one link, no markdown, no unconfirmed team names, no search links, no em dashes, silence for thanks | Copy written in three places drifts. The bot used to answer "thanks" with a refusal |
| D34 | **The emergency guard runs before the model.** Gas, fire, trapped, live cable and collapse are recognised locally and get "Call 999 now", never a report | Safety cannot depend on a model call that might fail, and a gas leak is not a litter report |
| D27 | **`deepseek-flash` is DeepSeek V4.1 Flash and handles text and images, so it is the only provider we need.** Effort pinned to `low`, and every DeepSeek request carries `reasoning` | Cheaper on both sides of the token count and faster than V4 Pro on the same prompt. Without the `reasoning` key an image request returns HTTP 200 with empty content, reproduced twice |
| D28 | **The model proposes and `code/triage.py` decides.** Unknown category, no location, `info_only` and `not_council` are refused before `save_report` is called | A wrong row in the database is worse than a question back to the resident, and validation is testable without the network |
| D29 | **Duplicate matching allows extra words at the same place.** "Weston Lane" matches "Weston Lane outside the school". A directional suffix (north, south, east, west, upper, lower) still means a different road | Exact text matching missed a real repeat during the live check; the suffix guard keeps one street from swallowing its neighbours |
| D30 | **The bot remembers a location question for 10 minutes** and joins a short reply to the earlier message | Without it, "there is a pothole near my house" followed by "Alma Road" lost the report. A proper session store is deferred |
| D35 | **Real FixMyStreet reports may be used for the evaluation only.** Permission given by: ________ (fill in) on ____-__-__ (fill in). Covers: Southampton reports from FixMyStreet's Open311 API, used unaltered (names and details as published) by the evaluation in `code/eval/fms/` to score category accuracy and the duplicate rule. Not covered: the demo database, the council dashboard, the agent, or any committed file. Raw data stays in `code/eval/fms/raw/`, which is gitignored; committed files hold FixMyStreet ids and our labels only. Credit mySociety/FixMyStreet in `NUMBERS.md` and the README. This is an exception to the `CLAUDE.md` rule against using individual FixMyStreet reports, which should be updated to point here | The brief names FixMyStreet as the starting point, and 60 synthetic messages written by us would only test our own phrasing. Signed: Aadil |

## Proposed: drop-a-pin location link (not wired in yet)

| # | Proposal | Why | Proposed by |
|---|---|---|---|
| D35 | **When a report has no street, also offer a map link.** `code/pin_service.py` is built and tested but the bot does not call it yet. The changes below are for the owners of `blue_bubbles.py` (Section 1) and `messages.py` (Section 2) to make | A map pin is faster and more accurate than typing a street, and it works for residents who do not know the road name. Privacy design and legal notes in `COMPLIANCE_LOCATION.md` | Anirudh |

**Where it is called (Section 1, `code/blue_bubbles.py`).** In `reply_for`, in the `reason == "no_location"` branch, after `tools.save_report(...)` succeeds and `remember_location(...)` runs:

```python
pin_url = None
if os.getenv("PIN_BASE_URL"):  # off unless the pin service is running behind HTTPS
    import pin_service
    pin_url = pin_service.create_location_link(saved["report_id"])  # passes only R-0074, never the sender
return messages.need_location(decision, pin_url=pin_url)
```

`create_location_link` reads `BASE_URL`. The bot should set it from `PIN_BASE_URL`, or the two can share one variable.

**The text (Section 2, `code/messages.py`).** `need_location(decision, pin_url=None)` keeps today's reply when `pin_url` is None. With a link, placeholder wording, still three lines and one URL:

> Logged: fly-tipping.
> Where exactly is it? Drop a pin on this map: <pin_url>
> Or just reply with the street name.

**How the bot reads the result.** Both processes run on the demo Mac, so the simplest route is a direct call, `pin_service.get_location(report_id)`, with `SOTONFIX_DB` pointing at the same file. From another machine, use `GET /api/location/<report_id>` with header `X-Api-Key: $BOT_API_KEY`. That returns the same dict plus a ready-made `location_text`. Two moments to read it:
1. **When the next message arrives from someone with a `_pending` entry**, check `get_location` first. If a pin was confirmed, use it and treat the message as normal.
2. **Optionally**, a background check every 30 seconds over `_pending` entries. When a location appears, call `reports_db.set_location` and send `messages.logged(...)`, so the resident gets a confirmation without texting again.

**How the fields map onto the report.**
- `reports.location` is `pin_service.as_report_location(loc)`, for example `Windsor Terrace, near The Bargate, SO14 7BQ`, written with the existing `reports_db.set_location`.
- The street comes first on purpose. `tools._same_place` allows extra words after a street, so duplicate matching against an earlier "Windsor Terrace" report still works.
- `reports.area` (the new column from f77dd7e) takes `loc["area"]`. That needs a small setter in `reports_db.py`, which Section 3 owns.
- `coverage == "unverified"` means we could not confirm it is in Southampton. Keep the report and let the officer see a flag (Section 3).

**Coordinates stay off by default.** `STORE_COORDINATES` is unset, so the pin service keeps no latitude or longitude, which matches D26 and the "never store coordinates" rule. Turning it on stores them rounded to about 11 m, only in `code/pin.db` and never in `kerbside.db`.

**Overlap with TODO-SPLIT 1.1 and 1.7, please read.**
- **1.1 (Apple Maps pins in a text)** also reverse geocodes with Nominatim, in the bot process. Two separate rate limiters could together break Nominatim's one-request-per-second rule. Suggest 1.1 reuses `pin_service.assess(lat, lng)`. That gives one geocoder, one lock and cache, the same Southampton check (bounding box, then postcodes.io council area) and the same sanitising, with no coordinates stored. `code/location.py` currently returns coordinates and has no timeout on its wait, so it is better not to use it for this.
- **1.7 (maps plugin attachments)**: no code conflict. A shared Apple Maps location and a confirmed pin are two routes to the same location field. Whichever arrives first wins, and the other should not overwrite it without the resident asking.
- **1.4 (incomplete reports)**: once a pin fills the location, duplicate matching should run again on the real street, never on "Not given".

**To run it:** `python code/pin_service.py` (port 5007) behind an HTTPS tunnel with `TRUST_PROXY=1`, `BASE_URL=https://<host>`, `CONTROLLER_NAME`, `CONTACT_EMAIL` and `SOTONFIX_USER_AGENT` set. Phones refuse location sharing on plain HTTP.

## Graph runtime decisions (D61 to D64)

**D61. One write path, and it is `tools.save_report`.** The graph calls it with
`capture_state` and `routing_status`; `turn_operations (turn_id, "commit")`
makes a replay safe. A detail calls `tools.update_report_location` or
`tools.attach_photo_to_report` against the open report id, never a second insert.

**D62. A follow-up is not a new incident when the open report already has a
description and the message is a place, a photo or "still there".** `capture`
preserves the description; `execute` updates the active row. A different problem
noun or category still creates a new row. This is what makes the restart fixture
show one row at Weston Lane, not two.

**D63. The channel is cut over by `MODE=graph`, and the simulator defaults to
graph.** `MODE=legacy` keeps the old `TriageAgent` path for the 96 legacy tests
and for a rollback. The webhook sends the bubbles, then the private report link,
then a checked source link. The checkpoint holds no raw phone in the process
runtime; the thread store holds only the salted reporter reference.

**D64. Copy is template-first through the freeze.** `messages` supplies the
wording, `compose` splits it into at most three bubbles, `lint` checks schema,
URL and claim rules against the executed outcome. A model may rewrite the
bubbles after the freeze only through the same lint gate. This keeps the demo
truthful when the model is unavailable and preserves the natural, short register.

## D65: personal profile override

The operator explicitly overrides the earlier no-PII rule for this pilot. A separate
`profiles` table may store a preferred name, address and phone, keyed by the salted
reporter reference. The reports table, the resident page `/r/<token>` and the public
dashboard never carry those fields. The writer may use the first name; it never reads
the phone back. Only those three fields are stored; other details are asked when a
report is filled in. This supersedes D26 and the no-name/no-phone rule for this build.

## How to change something

1. Write the line in this file first: what, why, who.
2. If it touches a contract, message the file owner and let them merge it.
3. If it adds scope, say what is being dropped to pay for it.

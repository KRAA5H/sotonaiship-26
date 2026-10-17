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

## How to change something

1. Write the line in this file first: what, why, who.
2. If it touches a contract, message the file owner and let them merge it.
3. If it adds scope, say what is being dropped to pay for it.

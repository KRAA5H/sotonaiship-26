# Worklog

**Read this first if you have been away.** Newest entries at the top. One line per action, with the file and the reason. Nothing happens that is not written here.

Three places, no more:
- **`WORKLOG.md`** (this file): what happened, when.
- **`DECISIONS.md`**: what we chose and what we rejected, so nobody re-opens it.
- **`PLAN.md`**: what we are building. Source of truth.

---

## 23:25, Saturday: a simulator while the Mac is away

- `code/simulator.py`: a second app on port 5007, mobile-first, no BlueBubbles. It runs the real triage, voice, reply and save path, keeps a per-browser reporter id, and shows the debug decision, model time and typing time.
- Simulated latency: 350ms plus 9ms per character, capped at 3.5s, toggleable. Links come back as a separate bubble after 0.8s, matching the real line.
- Photo upload works without the Mac: the bytes go straight to triage and the vision model.
- `blue_bubbles.detect_self_address()` moved out of import into startup, so `reply_for` can be imported without a Mac on the network. That was blocking the simulator.
- Tests: 301 pass, 31 evaluation cases. Live turn: broken glass on Alma Road saved `R-0102`, body and link split, 4.1s model, 1.5s simulated typing.
- Run: `python code/simulator.py`, then http://192.168.0.202:5007 on a phone on the same wifi.

## 23:05, Saturday: text stops thinking

- DeepSeek ignores `reasoning: {effort: none}`, `enabled: false` and `reasoning_effort: none`, but `thinking: {"type": "disabled"}` really works: output dropped from 64 to 170 tokens to 3 to 4, with no reasoning content.
- `llm.py`: text candidates no longer request reasoning and send `thinking: disabled`; image candidates keep `reasoning: low` because without it DeepSeek returns empty content.
- Tests: 294 pass (new `test_llm.py`, 5 payload cases), 31 evaluation cases.
- Live: a glass report on Alma Road answered normally; a photo was still described correctly ("packet of biscuits on a desk").
- Honest note: the model call is still about 1.2 to 1.7 seconds, so the gain is cost and less thinking, not much wall clock.

## 22:50, Saturday: links as their own text, and pins wired

- **Links are a second message.** `deliver()` splits the words from the link and sends the link on its own after `LINK_DELAY` (0.8s). A follow-it line, a council page, a finder link: all arrive as a normal human follow-up. Live proof: "got it, pothole logged on Alma Road..." then the report link as a separate send.
- **Shared pins now reach the message flow.** `place_from_text()` parses `coordinate=lat,lon` from Apple and Google map links, `LocationService.reverse_geocode` turns it into a street and area, and `apply_place()` fills the missing location instead of asking for it. A pin with no words keeps the place and asks "what's the problem there?"; the next message uses it. A pin outside Southampton gets the council finder, sent as its own link.
- Live: pin at 50.9097,-1.4044 became Floral Walk (The Polygon); a pin then "there is a pothole here" saved `R-0098`; a pin inside a sentence saved `R-0099`; a London pin replied with Charing Cross and the finder link.
- Tests: 289 pass, 31 evaluation cases.

## 22:20, Saturday: independent audit and fixes

Three read-only audits ran over section 2: code review, evidence check, goal check. The functional claims held, the numbers and four behaviours did not.

- **Fixed, critical:** two messages for the same sender could run two turns at once (concurrent `handle_inbound`, double reports, a question asked after it was answered). One turn per sender now, with the second message queued and handled after; a test sleeps inside a turn and asserts one save.
- **Fixed, high:** `merge_pending` deleted the pending report before validating the follow-up, so a long answer lost it. The voice prompt still carried a banned exemplar, so the no-answer path kept falling back. The photo ask was computed but never enforced by the lint. The status lint could accept "now closed" against "being looked at". Bare domains passed the URL rule, and "a crew will be out soon" passed the timescale rule. A late photo with two open reports became a junk "Not given" report instead of a question. The motorway refusal appended a Hampshire streetlight page. A crash sent "that is logged" when nothing was. The incomplete path never asked for a photo.
- **Now:** 280 tests and 31 evaluation cases pass. Live: `R-0092` pothole with a photo ask, `R-0093` from two messages 0.7s apart (one reply), a parking question answered with "tell me a bit more", a late photo attached to `R-0093`, resident page and photo both 200.
- **Still open, stated plainly:** a message that lands during the 3 to 4 second voice call gets its own later turn (no double save, but two replies); `python code/website.py` alone does not register the photo route; evaluation cases 3 and 17 are weaker than they look; the attachment guid appears in BlueBubbles log lines; the photo route can block for 45 seconds if the Mac sleeps; the council page is still the third line on a no-answer.

## 21:15, Saturday: bursts and no deflection

- **Bursts.** A per-sender 2.5 second quiet window (`enqueue_message`, `flush_burst`), and anything that arrives while we are thinking is folded into the same turn before saving (`take_pending`). Ten out of ten double-texts used to get two replies; now they get one. Live: two messages 0.8s apart became one report, `R-0083`, with both facts and one reply.
- **No deflection.** Removed "not sure", "no checked answer", "honestly", "don't know" from the templates, the brief, the prompt and the lint. The council page is now the last line, never the opening. A question we cannot settle gets "tell me a bit more and i'll point you the right way" instead of a form.
- Voice budget raised to 700 tokens after DeepSeek returned empty content twice under a 400 token floor; three of three samples then passed lint.
- Tests: 269 pass, 31 message-evaluation cases. A question now takes about 12 seconds: 2.5 quiet window, triage, a retrieval attempt, then the voice call. Speed is Section 1.

## 22:40, Saturday: section 2, the resident's voice

- `code/voice.py`: the model writes the sentence, we keep the facts. 22 spoken category names, a brief per path, a lint over every reply, and the existing templates as the fallback. `code/test_voice.py` has 51 offline tests.
- The register is a friendly young council employee. "ah, that one's not ours, sorry. National Highways handles motorways, so give them a ring on 0300 123 5000." Rejections: corporate phrases, invented timescales and numbers, unconfirmed team names, URLs, markdown, em dashes.
- A photo is now requested on every saved report, in the same reply, and the templates carry the same line.
- A photo sent later attaches to the sender's single open report through `code/photos.py`. The Maps plugin payload is never treated as a photo.
- The resident page shows their own photo through `GET /r/<token>/photo`, token-only, no store, no guid in any URL. Photo bytes stay in BlueBubbles; the database holds two reference columns.
- Live run: 7 messages. Casual duplicate and refusal replies, silence on thanks, a status answer, a grounded answer, a late photo attached to `R-0079`, resident page 200, photo 200 at 826 KB.
- Tests: 268 pass (voice 51, photos 25, bot 41, tools 47, website 31, messages 23, triage 25, rag 25), plus 31 message-evaluation cases.

## 21:40, Saturday: RAG and the resident voice (phase 1)

- `code/rag.py`: grounded answers. All 53 dated facts go in one prompt and the model cites fact numbers, so there is no vector database and no keyword list. 12 of 12 live questions cite the right fact, and 2 of 2 unanswerable questions are refused cleanly.
- `code/messages.py`: every resident string in one module. The copy rules are tests: three lines, one link, no markdown, no unconfirmed team names, no search links, no em dashes.
- Act first: a report with no street is saved as "Not given", and the resident's answer updates that row instead of creating a second report.
- Status: "any update?" is answered from the database against that sender's latest report, with no model call.
- Emergency: gas, fire, trapped, live cable and collapse get "Call 999 now" before the model is called, and nothing is saved.
- Tests: 177 pass (triage 25, tools 43, website 31, bot 33, rag 24, messages 21), plus 18 message-evaluation cases and 12 live RAG cases.
- Live run: nine texts through the real server and model. Two reports saved, one incomplete waiting for a street, one grounded answer with a source, one status answer, one silence, one greeting, one 999 reply, one National Highways reply.
- Found and fixed while testing: the bot answered a thank you with a refusal, a missing street threw the report away, and an unanswerable question still got a citation.

## 19:20, Saturday: v1 joined

Gate G1 met and beaten: one iMessage becomes one row, one card and one link.

- `code/triage.py`: new. One DeepSeek call returns JSON (category, location, description, severity, confidence). We validate it, the model does not. Unknown category, missing location and info-only outcomes are refused before any write.
- `code/blue_bubbles.py`: `MODE=triage` saves a report and replies with `/r/<token>`. `MODE=echo` kept as a plain chat fallback. A short follow-up after "where is it?" is joined to the earlier message instead of being lost.
- `code/llm.py`: DeepSeek V4.1 Flash now reads photos natively. Two faults fixed: an image request without `reasoning` returns 200 with empty content, and an empty content is retried once before moving down the ladder.
- `code/tools.py`: duplicate matching accepts extra words at the same place ("Weston Lane" vs "Weston Lane outside the school") and refuses directional suffixes.
- Tests: 106 pass. `test_triage.py` 25, `test_tools.py` 38, `test_website.py` 31, `test_bot.py` 12.
- Verified live: real pothole text, real iMessage reply delivered, row `R-0069`, resident page 200, council page shows it.
- Fixed in passing: two servers were bound to port 5005 at once, which would have double-replied. One server now.

## State at 16:50, Saturday

| | |
|---|---|
| Docs | Final. `PLAN.md` v2, `DECISIONS.md`, `VIDEO.md`, `CRITIQUE-vs-GOMER.md` |
| Product code | Superseded: see `PLAN.md` section 0 for current status |
| Can it run? | Not yet. Flask, requests, python-dotenv and anthropic were missing on this machine and are now installed. No `.env`, no API key |
| Duplicates | `blue_bubbles.py`, `conversational_ai.py`, `database.py` exist at the repo root and in `code/`. Frozen at the root, `code/` is the home (D17) |
| Next gate | **G1, 18:00: one message becomes a row in the database and a card on screen** |
| Uncommitted | `PLAN.md`, `DECISIONS.md`, `VIDEO.md`, `CRITIQUE-vs-GOMER.md` |

---

## Log

### Sat 17 Oct, late, code: multi-agent workflow and the location system (branch `aadil/agents`)
- `code/agents/`: the triage agent orchestrates safety, location, photo (parallel), category, duplicate, records, reply and status agents, per `plans/agents.md` (DECISIONS.md D45).
- `code/llm.py`: DeepSeek with thinking off for every call; an empty image reply is the only retry with thinking (D46). Every call logs tokens and latency, never text.
- Location: `code/geo/` holds Southampton's real boundary and 2,192 streets from OpenStreetMap. The bot serves the map page on its own address; the page has "use my current location", a street drop-down filtered on the phone, and a visible pin drop. A confirmed pin updates the report and texts the resident. Typed streets and iMessage location cards are handled with no model call (D47).
- Fixed: TODO 1.2, 1.3, 1.4, 1.5 and most of 1.1 and 1.7; neighbour problems go to the council form (D48); per-category duplicate windows (D49); `save_report` no longer waits on Nominatim when the street is known.
- Tests: `test_agents.py` (36), `test_geo.py` (14), new pin and simulator tests; all 16 suites pass offline. Walked the location flow in headless Edge at phone size. Live model check: `python code/agents/smoke.py`, not run here (no key on this machine).

### after 17:55, code and docs, reports database and agent tools
- New `code/reports_db.py`: builds `code/kerbside.db` from `dashboard/schema.sql` and loads the 68 synthetic reports. The `.db` file is gitignored.
- New `code/tools.py`: `find_category_facts`, `check_duplicate`, `save_report`, `get_report_status`, tool schemas and `call_tool()`. New `code/test_tools.py`: 34 tests, standard library only, all passing.
- Duplicate rule is now open report (new or in_review), same category, same location text, 30 days. `agent/categories.json` updated, the 50 m radius removed.
- `dashboard/make_fake_reports.py`: no report dated after the newest original, repeats only link to open reports, and it refreshes the copy embedded in the prototype. Data regenerated.
- `agent/loader.py` reads files as UTF-8 (a pound sign was breaking on Windows).
- `DECISIONS.md` D26: `CLAUDE.md` and `schema.sql` reports replace `PLAN.md` section 4.
- `PLAN.md`: new section 0 with status, open questions and the next backend tasks.
- On branch `aadil/agent-tools` (pushed), not merged into `main`. The tools are not wired into `blue_bubbles.py` yet. `database.py` untouched on request.

### 17:55, code, photos work
- `bb.download_attachment`: `GET /api/v1/attachment/<guid>/download`. Omit `original` and the server converts HEIC to JPEG; `width=1024` returns PNG. No Private API needed. Confirmed from the server source by the research agent.
- `llm.chat(system, user, image)`: sends the image as a data URI to a separate `LLM_VISION_MODEL`, with `reasoning.effort=low` and 800 tokens, because reasoning models otherwise return empty `content`.
- Vision model: `nvidia/nemotron-3.5-super-vl:free`, 10.5 to 12.2s, read a real inbound photo correctly and said it was not a council issue. Gemma models returned 429, inkling returned 403 (agentic harness only), dots-3 returned empty.
- Webhook now downloads the first attachment and answers with what it saw. Verified end to end with a throwaway chat id: `vision=True`.

### 17:35, code, guards after real traffic
- Real traffic proved inbound: 51 webhook deliveries from `192.168.0.26`, replies delivered to `anirudh.udupi@gmail.com` and the self chat.
- Fixed a reasoning leak: some models return empty `content` and a populated `reasoning` field, and the old fallback sent the reasoning to a resident. `llm.py` now retries, then uses the stub, and never sends reasoning.
- Fixed a self-chat loop: replying to the server's own address arrives back as an inbound message. `IGNORE_SENDERS` plus the auto-detected self address now blocks it.
- Fixed duplicate replies: the webhook returns 200 immediately and replies from a thread, and it deduplicates on the inbound message GUID.
- Added `STALE_SECONDS` so a restart cannot answer the replayed backlog.
- Verified: `ignored_self`, `ignored_stale`, `duplicate`, zero sends. Deleted old webhook id 2, only id 3 (LAN) remains.
- Launched a read-only researcher for the BlueBubbles attachment download endpoint (unblocks photos).

### 17:20, verification, no code changes
- Re-verified after re-approval: all six files present, Flask healthy on `192.168.0.202:5005`, ping 200, one-shot model reply in 11.1s, synthetic webhook returned `mode=model sent=true`.
- Windows firewall rule could not be created without admin (`Access is denied`), so the Mac to Windows hop is still unverified. Old webhook id 2 pointing at `localhost:5005` still needs deleting.
- Only open plan item is the real inbound test from a second device.

### 17:10, code, implemented and verified
- New: `code/bb.py`, `code/send_test.py`, `code/llm.py`, `code/echo_ai.py`, `code/.env.example`, `code/requirements.txt`. `code/.env` exists locally and is gitignored.
- Rewrote `code/blue_bubbles.py`: `MODE=echo` or `agent`, lazy `IntakeAgent` so echo mode needs no Anthropic key, `/health`, `host=0.0.0.0:5005`.
- Verified: ping 200; sent to `anirudh.udupi@gmail.com` and to self; emoji and two-line messages; model reply in 8.0s and delivered; stub mode with no key; wrong password fails once with 401 and no traceback; `POST /webhook` returned `mode=model sent=true`; `isFromMe` payloads ignored.
- Findings: creating a chat requires a first message on macOS Big Sur and later (500 otherwise), so `ensure_chat` creates and sends in one call; `message` is the correct send field on 1.9.9; `openrouter/free` returned junk and was replaced; an old webhook (id 2) points at `localhost:5005` and should be removed by whoever created it.
- Registered webhook id 3: `http://192.168.0.202:5005/webhook` for `new-message`.

### 17:00, docs and verification, no code
- `plans/imessage-first.md` rewritten short, per request. Plan is a one-shot build now.
- Cleared seven stale todos. The board carries only live development work (D25).
- Verified BlueBubbles: 1.9.9, `private_api: false`, chat list needs `POST /api/v1/chat/query`, GUIDs use `any;-;`.
- Verified OpenRouter: key works, `openrouter/free` is 0 cost, text and image input, 200k context, returned `ok`.

### 16:45, docs, no code
- `PLAN.md`: removed human-to-human chat everywhere (D5). Officer can send a one-way status update only. Added the "is there a human on the other side" answer: no, the model is the counterpart.
- `DECISIONS.md`: created. D1 to D22, including the four reversals you asked for.
- `CRITIQUE-vs-GOMER.md`: marked advisory and partly overruled, so it cannot contradict the plan.
- `VIDEO.md`: header pointing at `DECISIONS.md`, plus D10 (photo-only opening).

### 16:35, docs, no code
- `PLAN.md` rewritten as v2 and made authoritative: scope freeze, frozen contracts (vocabulary, report JSON, endpoints, tables, interfaces), four-person file ownership, re-baselined gates from 16:40, the seven frozen demo beats. v1 is in git history.
- Reversals applied per your instruction: the volume-based problem statement stays (D1), and the agent-executes-every-step framing stays (D2).

### 16:20, docs, no code
- `CRITIQUE-vs-GOMER.md`: created, then extended with section 2.5 on his one concession (a very specific bot for residents with low literacy). Refined the question rule into "clarify rarely, confirm-back routinely".

### 15:50, docs, no code
- `VIDEO.md`: created. Trailer with a real product spine, beat sheet to 2:40, AI b-roll prompts, capture checklist, edit settings, fallback if the build is late.

### 15:10, docs, no code
- `PLAN.md` v1: created.
- Verified by request from this machine, not taken on trust: FixMyStreet Open311 (200, real reports with photos, 1000 cap, rate limited), Open-Meteo forecast (keyless, soil temperature and moisture), Open-Meteo marine (`sea_level_height_msl`, keyless tide), Open-Meteo flood (river discharge), EA flood-monitoring (0 warnings on a dry day), Southampton's Empro portal, Balfour Beatty Southampton Highways Partnership and Causeway Confirm, BlueBubbles API shape and its macOS requirement.
- `todo`: items 1 to 11, covering the must-change list and tonight's build.

### 14:58, reading
- Read the Southampton City brief, judging and scoring, submission requirements, data sources, the Street Report Triage pitch PDF, and the schedule. Nothing written.

---

## Protocol from now on

Every turn ends with one line here: time, what changed, which file, why. If a turn changes nothing, it says so. If a decision changes, it goes in `DECISIONS.md` first. If a gate is hit or missed, it is recorded above.

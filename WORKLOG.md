# Worklog

**Read this first if you have been away.** Newest entries at the top. One line per action, with the file and the reason. Nothing happens that is not written here.

Three places, no more:
- **`WORKLOG.md`** (this file): what happened, when.
- **`DECISIONS.md`**: what we chose and what we rejected, so nobody re-opens it.
- **`PLAN.md`**: what we are building. Source of truth.

---

## State at 16:50, Saturday

| | |
|---|---|
| Docs | Final. `PLAN.md` v2, `DECISIONS.md`, `VIDEO.md`, `CRITIQUE-vs-GOMER.md` |
| Product code | **I have not changed a line.** The three modules in `code/` are yours and are untouched |
| Can it run? | Not yet. Flask, requests, python-dotenv and anthropic were missing on this machine and are now installed. No `.env`, no API key |
| Duplicates | `blue_bubbles.py`, `conversational_ai.py`, `database.py` exist at the repo root and in `code/`. Frozen at the root, `code/` is the home (D17) |
| Next gate | **G1, 18:00: one message becomes a row in the database and a card on screen** |
| Uncommitted | `PLAN.md`, `DECISIONS.md`, `VIDEO.md`, `CRITIQUE-vs-GOMER.md` |

---

## Log

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

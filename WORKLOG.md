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

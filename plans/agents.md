# Kerbside agents

## Orchestrator: the triage agent

The triage agent is the orchestrator (decided 17 Oct, DECISIONS.md D45). It receives every inbound message, keeps the conversation state (pending report, a shared pin, who to reply to), calls the agents below in order, and hands back the one text the resident gets. Its own job, classifying the message, is the only model call on the happy path. Code: `code/agents/triage_agent.py`; the channel (`code/blue_bubbles.py`, `code/simulator.py`) only delivers what it returns.

## Core agents, in the order they run

| # | Agent | Job | Uses an LLM? | Runs |
|---|---|---|---|---|
| 1 | **Safety agent** | Spots emergencies (gas smell, injury, fire, danger to life) and replies "call 999" before anything else happens. Also catches abuse and spam | Rules first, triage as a second net | First, on every message |
| 2 | **Triage agent** | Decides what the message is (report, question, unclear, out of area) and picks category, severity and any location it contains | Yes, one call | After safety |
| 3 | **Photo agent** | Reads the photo and returns structured features: what is visible, size, surface, hazard, short label. Never invents a location | Yes (vision) | In parallel with triage, only if a photo is attached |
| 4 | **Category agent** (one per category, see below) | Owns everything specific to that kind of problem: required fields, follow-up question, severity rules, owning team, form link, duplicate rules | No, code driven by config | After triage picks the category |
| 5 | **Location agent** | When the location is missing, offers three ways: tap the map pin link, type the street name, or share location (including Apple Maps pins). Checks it is inside Southampton, saves the street only | No, code | When a report has no usable location |
| 6 | **Duplicate agent** | Blocks the same person logging the same thing twice. Merges different people's reports of the same problem into one job. Uses the category agent's radius and time window. Never matches on a missing location | No, code (text similarity optional) | Once the location is known |
| 7 | **Records agent** | Saves the report, issues the reference, and sends it to the council side (database and dashboard) in a clean structured format | No, code | After duplicate check passes |
| 8 | **Reply agent** | Writes every outgoing text from the facts the other agents supply (category, street, reference, status, one link). Falls back to a template if the text fails the style check | Yes | Last step of every message |
| 9 | **Status agent** | Texts the resident when the council changes a report's status, especially when it is marked fixed. Cuts "has it been fixed?" chaser calls | No, triggers the Reply agent | When a report's status changes, not when a resident messages |

## Category agents (the specialists behind agent 4)

Triage picks the category, then hands the report to that category's specialist. Owners marked "confirm" must be checked against `categories.json` and a council contact before claiming them in the pitch.

| Category agent | What it knows and checks | Likely owner (confirm) | Duplicate rule |
|---|---|---|---|
| **Fly-tipping** | Item type and size (bag or van load), hazardous items (needles, asbestos, chemicals), council land vs private land | Street cleansing | Same spot, 7 days |
| **Pothole and road defect** | Road vs pavement, size and depth, busy road or near a school. Ranks by risk of harm and claims | Highways partnership (Balfour Beatty Living Places) | Same spot, 30 days |
| **Graffiti** | Offensive or not, public vs private wall. Offensive jumps priority | Street cleansing | Same wall, 14 days |
| **Litter, glass and dog fouling** | Broken glass on a path or road is urgent. Where and how much | Street cleansing | Same spot, 3 days |
| **Streetlight** | One light or a whole street out, column number if visible, dark area near a crossing or path | Highways | Same column, 14 days |
| **Abandoned vehicle** | Registration plate, how long it has been there, any damage | Council enforcement | Same plate |
| **Missed bin** | Address, bin type, collection day. Needs a house, not a pin | Waste services | Same address and day |
| **Trees, hedges and leaves** | Fallen or blocking a road is urgent, overgrown is routine | Parks or highways | Same tree, 14 days |
| **Noise and neighbour nuisance** | Sensitive: sends the council form instead of taking a pin, so we do not log someone's home | Environmental health | Form handoff only |
| **Not ours and unclear** | Sends the council form when triage is unsure, or points to the right body (water company, Network Rail, police non-emergency) | n/a | n/a |

### What each category agent returns to the orchestrator

Missing fields, the follow-up question to ask, severity, owning team, form link, duplicate radius in metres and duplicate window in days.

## How to build it so it is finishable

- **One shared base class, one config entry per category.** Extend `categories.json` with `required_fields`, `follow_up_questions`, `severity_rules`, `owner`, `form_url`, `dup_radius_m`, `dup_window_days` and `photo_features`. Each agent is that config plus an optional override.
- **No extra model call per category.** Category agents are code driven by config. The model is used only in triage and, when a photo is attached, in the photo agent asking for category-specific features.
- **Go deep on three, config-only on the rest.** Fly-tipping, pothole and graffiti are what the bot already handles, so make those excellent and demo them.

## How a message flows

Message in, Orchestrator, Safety check, then Triage and Photo in parallel. Triage picks the category and the matching Category agent takes over. If it is "not ours" or unclear, the form link goes out and the flow ends. If there is no location, the Location agent asks and the flow waits for the answer. Then the Duplicate agent, the Records agent, and finally the Reply agent texts the resident.

Separate path: council marks a report fixed, the Status agent triggers the Reply agent, resident is texted.

## Built (branch `aadil/agents`)

| # | Agent | File | Notes |
|---|---|---|---|
| | Orchestrator = triage agent | `code/agents/triage_agent.py` | `handle(turn)` returns the reply plus a trace of every agent and its milliseconds |
| 1 | Safety | `code/agents/safety.py` | 999, threats and spam by rules, then a second net after triage. Fixed words, never the model |
| 2 | Triage | `code/triage.py` (the model call) | DeepSeek, thinking off, temperature 0.1, 10 s timeout |
| 3 | Photo | `code/agents/photo.py` | Starts in parallel with triage; features stored when ready, never waited for |
| 4 | Category | `code/agents/categories.py` | One base class plus fly-tipping, pothole and graffiti specialists, all driven by the `agent` block in `categories.json` |
| 5 | Location | `code/agents/location_agent.py`, `code/geo/`, `code/pin_service.py`, `code/pin/static/` | Map link, typed street (offline, no model), shared pin or iMessage location card. Southampton's real boundary, never a postcode prefix |
| 6 | Duplicate | `code/agents/duplicate.py` | Same person: nothing new. Someone else: linked. Per-category window, never on a missing location |
| 7 | Records | `code/agents/records.py` | The only writer |
| 8 | Reply | `code/agents/reply.py` (uses `code/voice.py`) | Model words checked by the style lint, template on doubt or delay (6 s) |
| 9 | Status | `code/agents/status.py` | Council changes a status on the dashboard, the resident is texted |

Where this differs from the table above, deliberately:
- Streetlight and trees have no category agent: neither is a confirmed category in `categories.json`, so triage sends them to `council_service_other`.
- Missed bins use a 7 day window (one collection cycle), not "same day": a bin still not emptied two days later is the same missed collection.
- Owners stay dashboard-only. `team_confirmed` is false everywhere, so no team is ever named to a resident.

Live check with the real model: `python code/agents/smoke.py` (needs `DEEPSEEK_API_KEY`).

## Rules to keep it fast and trustworthy

- Only agents 2, 3 and 8 call a model. Every extra model call slows the reply, and the open-work doc asks for one model call on the happy path.
- Build them as separate modules behind the orchestrator, not separate services. It gives the multi-agent story without the integration risk.
- iMessage cannot show an interactive map in the chat. The Location agent sends a link that opens the map page, and the street-name and shared-location options work as normal replies.
- "Same user" and "same problem" are two different checks inside the Duplicate agent.
- The Safety agent must never be skipped, and its reply must never be reworded into something vague.

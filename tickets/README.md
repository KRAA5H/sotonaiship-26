# Tickets database + MCP server

The MCP server the AI agent uses to read council services and save complaints, kept in sync with the council website and the iMessage bot, so every complaint exists once and shows everywhere.

- `db.py`: all tickets database access (SQLite now; swap this one file for Postgres later)
- `bridge.py`: two-way sync with the website's database (`code/kerbside.db`)
- `server.py`: MCP server (official `mcp` SDK v2, `MCPServer`)
- `test_client.py`: end-to-end test that calls every tool over MCP
- `test_bridge.py`: tests that everything is linked and nothing is repeated

## How it all links together

```
 iMessage bot ──(tools.save_report)──┐
                                     ▼
 Council website /council  ◄──►  code/kerbside.db  (reports)
 Resident page   /r/<token> ◄──┘        ▲
                                        │  bridge.py (sync)
 AI agent ──(MCP tools)──► tickets/tickets.db (tickets, actions, messages, audit_log)
```

- **A text to the bot** is saved in `reports`. The sync turns it into a ticket, so the MCP tools see it.
- **An MCP `create_ticket`** saves the report on the website first, through the teammates' own `tools.save_report`, then the linked ticket. It shows on `/council` at once, and `tracking_link` is the resident's `/r/<token>` page.
- **An officer's click on `/council`** moves the ticket on: *in review* makes it `APPROVED`, *resolved* makes it `COMPLETED`.
- **The sync timing:** it runs before every tool call, and every 10 seconds in the background.

| Website `reports` | MCP `tickets` |
|---|---|
| `id` (R-0042) | `report_id` (unique: one report = one ticket) |
| `link_token` | `tracking_token` (same private link) |
| `reporter_ref` | `reporter_ref` (same salted hash of the sender) |
| `category_id` / `description` / `location` | `category` / `summary` / `location_text` |
| `severity` high/medium/low | `urgency` 1/2/3 |
| `duplicate_of` (report id) | `duplicate_of` (ref_code of the original) |

| Ticket status | Website shows |
|---|---|
| RECEIVED, TRIAGED, NEEDS_INFO, PENDING_APPROVAL | `new` |
| APPROVED, ASSIGNED, IN_PROGRESS | `in_review` |
| COMPLETED, REJECTED | `resolved` |

### No repeated complaints
1. **One report, one ticket.** `report_id` is unique, and the sync never imports a report that is already linked.
2. **Same resident, same problem, still open.** `create_ticket` returns their existing ticket with `already_reported: true` and creates nothing. This also works across channels: someone who texted the bot and then reaches the agent is matched by the same hash.
3. **Different resident, same place.** They get their own ticket and link, marked `duplicate_of` the original on both sides, so `/council` groups them. `find_nearby_tickets` lists originals only, with an `also_reported_by` count. "Same place" means within `radius_m` when both have coordinates, otherwise the website's own street-name match.

## Setup

```powershell
cd tickets
py -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python bridge.py     # creates both databases if missing and links them
```

On Mac/Linux, use `python3 -m venv .venv` and `.venv/bin/python` instead.

## Environment variables (all optional)

| Variable | Default | What |
|---|---|---|
| `TICKETS_DB_PATH` | `tickets/tickets.db` | MCP tickets database (read/write). Git-ignored. |
| `DB_PATH` | `code/kerbside.db` | The website's database. Same variable the website uses, also read from `code/.env`. |
| `SITE_URL` | `http://localhost:5005` | Base of the resident links (`SITE_URL/r/<token>`). Same as the bot uses. |
| `REPORTER_SALT` | (dev salt) | Must match the bot's, so the same person gets the same hash. |
| `KERBSIDE_SYNC` | `1` | `0` runs the MCP alone, with its own 40 seed tickets and no website. |
| `SERVICES_PATH` | `agent/categories.json` | Services list (read-only). |
| `SERVICES_FACTS_PATH` | `agent/confirmed_with_websites.csv` | Confirmed facts with source links (read-only). |

A "service" is any category in `categories.json` with `"outcome": "council_report"` (16 right now).

## Run the server

```powershell
.\.venv\Scripts\python server.py
```

It talks over stdio, so it sits there waiting for a client; that's normal. Run the website (`python code/blue_bubbles.py` or `code/website.py`) on the same machine with the same `DB_PATH`.

## Test it

```powershell
.\.venv\Scripts\python test_client.py    # every MCP tool, rejections and repeats: 18/18
.\.venv\Scripts\python test_bridge.py    # linking and no-repeat rules: 10 tests
```

Both use throwaway databases, so the live ones are untouched.

**MCP Inspector** (needs Node.js):

```powershell
npx @modelcontextprotocol/inspector .\.venv\Scripts\python server.py
```

Open the URL it prints, click **Connect**, then **Tools** to call each tool by hand.

## Connect to Claude Desktop

Edit `%APPDATA%\Claude\claude_desktop_config.json` (Mac: `~/Library/Application Support/Claude/claude_desktop_config.json`) and use absolute paths:

```json
{
  "mcpServers": {
    "southampton-tickets": {
      "command": "C:\\path\\to\\sotonaiship-26\\tickets\\.venv\\Scripts\\python.exe",
      "args": ["C:\\path\\to\\sotonaiship-26\\tickets\\server.py"]
    }
  }
}
```

Restart Claude Desktop. The tools appear under the tools icon.

## Tools

| Tool | Does |
|---|---|
| `list_services()` | All categories the council handles |
| `find_service(category)` | Team, questions to ask, severity hints, form link, confirmed facts |
| `lookup_postcode(postcode)` | lat/lng, local authority, ward, `in_southampton` (postcodes.io) |
| `find_nearby_tickets(category, lat?, lng?, location_text?, radius_m=200)` | Open originals at the same place, from every channel |
| `create_ticket(phone, category, summary, location_text, urgency, postcode?, lat?, lng?)` | Saves it on both sides; returns `ref_code`, `status`, `tracking_link`, `already_reported`, `duplicate_of` |
| `propose_action(ref_code, team, priority, note)` | Records a proposal, sets `PENDING_APPROVAL`. Carries nothing out. |
| `get_ticket_status(ref_code)` | Status, `website_status`, `tracking_link`, latest action |

Rules enforced in code:
- Unknown categories are rejected.
- A ticket needs a location.
- `propose_action` only works from `TRIAGED` or `NEEDS_INFO`.
- Phone numbers, sender hashes and website report ids are never returned.
- There are no approve, assign, complete, reject or delete tools. Officers do that on `/council`.

## For teammates

**Use `db.py`, don't write SQL against the file directly** where you can. Above all, change ticket status only with:

```python
import db
db.set_status("SOT-AB12C", "ASSIGNED", actor="officer.jane")   # validates + writes audit_log
```

The sync pushes it to the website as `in_review`.

**Statuses** (exact strings):
`RECEIVED`, `TRIAGED`, `NEEDS_INFO`, `PENDING_APPROVAL`, `APPROVED`, `ASSIGNED`, `IN_PROGRESS`, `COMPLETED`, `REJECTED`

**Normal flow:** `RECEIVED → TRIAGED → PENDING_APPROVAL → APPROVED → ASSIGNED → IN_PROGRESS → COMPLETED`, or `REJECTED`.

**Tables**

| Table | Fields |
|---|---|
| `tickets` | `id`, `ref_code` (e.g. `SOT-AB12C`, shown to resident), `tracking_token` (= the website's `link_token`), `phone` (only for MCP-made tickets; texts only store a hash), `category`, `summary`, `location_text`, `postcode`, `lat`, `lng`, `urgency` (1 = most urgent … 3), `status`, `created_at`, `updated_at`, `report_id`, `reporter_ref`, `duplicate_of`, `web_status` |
| `actions` | `id`, `ticket_id`, `team`, `priority` (1–3), `note`, `status` (`PROPOSED`, then `APPROVED`/`REJECTED`), `approved_by`, `created_at` |
| `messages` | `id`, `ticket_id`, `phone`, `direction` (`in`/`out`), `body`, `created_at` |
| `audit_log` | `id`, `ticket_id`, `event`, `actor` (`ai_agent`, `sync:messages`, `sync:dashboard`, an officer…), `created_at` |

Times are UTC ISO strings.

- **Tracking page:** look tickets up by `tracking_token`, never by `id` or `ref_code`.
- **Notifications:** log every SMS you send to `messages` with `direction='out'`.
- **Seed data:** with the website linked, the tickets are the website's 68 synthetic reports. The MCP's own 40 fake tickets (real Southampton streets, phones in the Ofcom drama range `+447700900xxx`) are only used when `KERBSIDE_SYNC=0`. To start again, delete `tickets.db` and run `python bridge.py`.

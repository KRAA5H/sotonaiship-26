# Tickets database + MCP server

The live complaints database and the MCP server the AI agent uses to read council services and save tickets.

- `db.py`: all database access (SQLite now; swap this one file for Postgres later)
- `server.py`: MCP server (official `mcp` SDK v2, `MCPServer`)
- `test_client.py`: end-to-end test that calls every tool over MCP

## Setup

```powershell
cd tickets
py -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python db.py        # creates tickets.db and seeds 40 fake tickets if empty
```

On Mac/Linux, use `python3 -m venv .venv` and `.venv/bin/python` instead.

## Environment variables (all optional)

| Variable | Default | What |
|---|---|---|
| `TICKETS_DB_PATH` | `tickets/tickets.db` | Live complaints database (read/write). Git-ignored. |
| `SERVICES_PATH` | `agent/categories.json` | Services list (read-only). |
| `SERVICES_FACTS_PATH` | `agent/confirmed_with_websites.csv` | Confirmed facts with source links (read-only). |

A "service" is any category in `categories.json` with `"outcome": "council_report"` (16 right now).

## Run the server

```powershell
.\.venv\Scripts\python server.py
```

It talks over stdio, so it sits there waiting for a client; that's normal.

## Test it

```powershell
.\.venv\Scripts\python test_client.py
```

This uses a throwaway `test_tickets.db`, so the live database is untouched. It should end with `14/14 checks passed`.

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
| `find_nearby_tickets(lat, lng, category, radius_m=200)` | Open same-category tickets nearby (duplicates) |
| `create_ticket(phone, category, summary, location_text, urgency, postcode?, lat?, lng?)` | Saves the complaint; returns `ref_code`, `status` |
| `propose_action(ref_code, team, priority, note)` | Records a proposal, sets `PENDING_APPROVAL`. Carries nothing out. |
| `get_ticket_status(ref_code)` | Status + latest action |

Rules enforced in code: unknown categories are rejected, a ticket needs a location, `propose_action` only works from `TRIAGED`/`NEEDS_INFO`, and phone numbers and tracking tokens are never returned. There are no approve, assign, complete, reject or delete tools; those belong to the dashboard.

## For teammates

**Use `db.py`, don't write SQL against the file directly** where you can. Above all, change status only with:

```python
import db
db.set_status("SOT-AB12C", "APPROVED", actor="officer.jane")   # validates + writes audit_log
```

**Statuses** (exact strings):
`RECEIVED`, `TRIAGED`, `NEEDS_INFO`, `PENDING_APPROVAL`, `APPROVED`, `ASSIGNED`, `IN_PROGRESS`, `COMPLETED`, `REJECTED`

Normal flow: `RECEIVED → TRIAGED → PENDING_APPROVAL → APPROVED → ASSIGNED → IN_PROGRESS → COMPLETED` (or `REJECTED`). Tickets made by the agent are created as `RECEIVED` and moved to `TRIAGED` straight away.

**Tables**

| Table | Fields |
|---|---|
| `tickets` | `id`, `ref_code` (e.g. `SOT-AB12C`, shown to resident), `tracking_token` (43-char random, for the tracking page URL), `phone`, `category` (a service id), `summary`, `location_text`, `postcode`, `lat`, `lng`, `urgency` (1 = most urgent … 3), `status`, `created_at`, `updated_at` |
| `actions` | `id`, `ticket_id`, `team`, `priority` (1–3), `note`, `status` (`PROPOSED`, then `APPROVED`/`REJECTED` set by dashboard), `approved_by`, `created_at` |
| `messages` | `id`, `ticket_id`, `phone`, `direction` (`in`/`out`), `body`, `created_at` |
| `audit_log` | `id`, `ticket_id`, `event`, `actor`, `created_at` |

Times are UTC ISO strings, e.g. `2026-10-17T17:07:53Z`.

- **Tracking page:** look tickets up by `tracking_token`, never by `id` or `ref_code`.
- **Notifications:** log every SMS you send to `messages` with `direction='out'`.
- **Seed data:** 40 fake tickets on real Southampton streets, phones in the Ofcom drama range `+447700900xxx`. Two potholes ~45 m apart on Portswood Road demo duplicate detection. Delete `tickets.db` to reseed.

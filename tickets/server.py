"""MCP server the AI agent uses to read services and save complaints.

Run:  python server.py        (stdio, for Claude Desktop / MCP Inspector)
"""
import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError  # message is shown to the AI

import db

INSTRUCTIONS = """You help Southampton residents report problems to Southampton City Council.

Only handle issues that match a service from list_services. For each complaint:
1. Work out the category with list_services / find_service.
2. Get a location: where the PROBLEM is (street + nearest number or landmark).
3. If the resident gives a postcode, call lookup_postcode. If it is not in Southampton, do not create a ticket; tell them to contact their own council (https://www.gov.uk/find-local-council).
4. Call find_nearby_tickets to check for duplicates. If there is a matching open ticket, tell the resident its ref_code instead of creating a new one.
5. Call create_ticket, then propose_action. An officer approves every action; never tell the resident the fix is booked.

If the issue is out of scope, do not create a ticket. Tell the resident who to contact:
- Danger to life or crime in progress: 999
- Non-emergency police (e.g. dangerous parking with no restriction): 101
- Smell of gas: National Gas Emergency Service, 0800 111 999
- Water leaks, burst mains, sewers: their water company
- Motorways and trunk roads: National Highways, 0300 123 5000
Never give out phone numbers of residents. You cannot approve, assign, complete or reject tickets."""

mcp = MCPServer("southampton-tickets", instructions=INSTRUCTIONS)

PUBLIC_FIELDS = ["ref_code", "category", "summary", "location_text", "postcode",
                 "lat", "lng", "urgency", "status", "created_at", "updated_at"]


def public(ticket):
    """Strips phone and tracking_token before anything leaves the server."""
    return {k: ticket[k] for k in PUBLIC_FIELDS}


def require_service(category):
    services = db.load_services()
    if category not in services:
        raise ToolError(
            f"'{category}' is not a council service. Valid categories: {sorted(services)}"
        )
    return services[category]


@mcp.tool()
def list_services() -> list[dict]:
    """List every issue type the council handles through this service.

    Call this first if you are unsure which category a complaint fits.
    Returns id (use it as `category` in other tools), label, group and team.
    If a complaint fits none of these, it is out of scope: do not create a ticket.
    """
    return [
        {"id": c["id"], "label": c["label"], "group": c["group"], "team": c["team"]}
        for c in db.load_services().values()
    ]


@mcp.tool()
def find_service(category: str) -> dict:
    """Get full details for one service category (use the id from list_services).

    Returns the responsible team, what information to collect (required_fields,
    follow_up_questions), severity hints for setting urgency, the official
    council form and scope notes, and confirmed facts with source links
    (e.g. council response-time aims). Use this to decide urgency and which
    follow-up questions to ask the resident.
    """
    s = require_service(category)
    keys = ["id", "label", "team", "required_fields", "follow_up_questions", "severity_hints",
            "official_form_url", "form_scope_notes", "note", "source_url"]
    return {**{k: s.get(k) for k in keys}, "confirmed_facts": db.load_service_facts(category)}


@mcp.tool()
async def lookup_postcode(postcode: str) -> dict:
    """Look up a UK postcode (free postcodes.io API).

    Returns lat, lng, local_authority, ward and in_southampton (True only if
    the local authority is Southampton). Use in_southampton to decide if the
    council covers it. If the lookup fails, returns ok=False with an error;
    then ask the resident for a street name instead.
    """
    clean = postcode.strip().upper()
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(f"https://api.postcodes.io/postcodes/{clean}")
    except httpx.HTTPError as e:
        return {"ok": False, "postcode": clean, "error": f"Postcode service unavailable: {e.__class__.__name__}"}
    if r.status_code == 404:
        return {"ok": False, "postcode": clean, "error": "Postcode not found. Ask the resident to check it."}
    if r.status_code != 200:
        return {"ok": False, "postcode": clean, "error": f"Postcode service error (HTTP {r.status_code})"}
    p = r.json()["result"]
    return {
        "ok": True,
        "postcode": p["postcode"],
        "lat": p["latitude"],
        "lng": p["longitude"],
        "local_authority": p["admin_district"],
        "ward": p["admin_ward"],
        "in_southampton": p["admin_district"] == "Southampton",
    }


@mcp.tool()
def find_nearby_tickets(lat: float, lng: float, category: str, radius_m: int = 200) -> list[dict]:
    """Find OPEN tickets of the same category near a point, to detect duplicates.

    Call this before create_ticket. Results are nearest first, each with
    distance_m. If one clearly describes the same problem, give the resident
    that ref_code rather than creating a new ticket.
    """
    require_service(category)
    return [{**public(t), "distance_m": t["distance_m"]}
            for t in db.find_nearby_open(lat, lng, category, radius_m)]


@mcp.tool()
def create_ticket(
    phone: str,
    category: str,
    summary: str,
    location_text: str,
    urgency: int,
    postcode: str | None = None,
    lat: float | None = None,
    lng: float | None = None,
) -> dict:
    """Save a resident's complaint as a new ticket.

    Only call after you have a valid category and a location, and after
    checking find_nearby_tickets for duplicates.
    - phone: the resident's number (stored, never returned).
    - category: an id from list_services.
    - summary: one or two sentences describing the problem.
    - location_text: where the problem is, e.g. "outside 42 Portswood Road".
    - urgency: 1 (most urgent) to 3 (least). Use severity_hints from find_service.
    - postcode, lat, lng: optional; use values from lookup_postcode if you have them.
    Returns ref_code (give this to the resident) and status (TRIAGED).
    Next step: call propose_action.
    """
    require_service(category)
    if not (location_text or "").strip():
        raise ToolError("A location is required. Ask the resident where the problem is.")
    if urgency not in (1, 2, 3):
        raise ToolError("urgency must be 1 (most urgent), 2 or 3 (least urgent).")
    if (lat is None) != (lng is None):
        raise ToolError("Give both lat and lng, or neither.")
    t = db.create_ticket(phone, category, summary.strip(), location_text.strip(),
                         postcode, lat, lng, urgency)
    return {"ref_code": t["ref_code"], "status": t["status"]}


@mcp.tool()
def propose_action(ref_code: str, team: str, priority: int, note: str) -> dict:
    """Propose what the council should do about a ticket, for an officer to approve.

    This does NOT carry anything out. It records the proposal and sets the
    ticket to PENDING_APPROVAL; a council officer approves or rejects it on
    the dashboard. Only works on tickets in TRIAGED or NEEDS_INFO.
    - team: usually the team from find_service.
    - priority: 1 (most urgent) to 3.
    - note: the recommended action and why, for the officer.
    """
    t = db.get_ticket(ref_code.strip().upper())
    if not t:
        raise ToolError(f"No ticket with ref_code {ref_code}")
    if t["status"] not in ("TRIAGED", "NEEDS_INFO"):
        raise ToolError(
            f"Ticket {t['ref_code']} is {t['status']}. Actions can only be proposed for TRIAGED or NEEDS_INFO tickets."
        )
    if priority not in (1, 2, 3):
        raise ToolError("priority must be 1 (most urgent), 2 or 3.")
    db.add_action(t["ref_code"], team, priority, note)
    return {"ref_code": t["ref_code"], "status": "PENDING_APPROVAL"}


@mcp.tool()
def get_ticket_status(ref_code: str) -> dict:
    """Get the current status of a ticket by its ref_code (e.g. SOT-AB12C).

    Use when a resident asks for an update. Returns the ticket details,
    status, and the latest proposed action (team, priority, action status).
    """
    t = db.get_ticket(ref_code.strip().upper())
    if not t:
        raise ToolError(f"No ticket with ref_code {ref_code}")
    action = db.get_latest_action(t["id"])
    return {
        **public(t),
        "latest_action": action and {k: action[k] for k in ("team", "priority", "status", "created_at")},
    }


db.init_db()
db.seed_if_empty()

if __name__ == "__main__":
    mcp.run()

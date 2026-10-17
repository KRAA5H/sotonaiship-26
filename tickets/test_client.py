"""End-to-end test: starts server.py as a real MCP server over stdio and calls
every tool, including the cases that must be rejected.

Uses a throwaway database (test_tickets.db) so the live one is untouched.
Run:  python test_client.py
"""
import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = Path(__file__).resolve().parent
TEST_DB = HERE / "test_tickets.db"
PHONE = "+447700900123"
results = []


async def call(session, tool, args, expect_error=False):
    r = await session.call_tool(tool, args)
    text = r.content[0].text if r.content else ""
    data = r.structured_content
    if data is None:
        try:
            data = json.loads(text)
        except ValueError:
            data = text  # error messages are plain text
    if isinstance(data, dict) and set(data) == {"result"}:
        data = data["result"]  # list-returning tools are wrapped as {"result": [...]}
    ok = bool(r.is_error) == expect_error
    results.append(ok)
    label = "REJECTED" if r.is_error else "OK"
    print(f"\n{'PASS' if ok else 'FAIL'}  {tool}({json.dumps(args)}) -> {label}")
    shown = json.dumps(data, indent=2) if not isinstance(data, str) else data
    print("   " + shown[:700].replace("\n", "\n   ") + ("..." if len(shown) > 700 else ""))
    assert PHONE not in shown and "+4477009" not in shown, "phone number leaked!"
    return data


async def main():
    for f in HERE.glob("test_tickets.db*"):
        f.unlink()
    params = StdioServerParameters(
        command=sys.executable, args=[str(HERE / "server.py")],
        env={**os.environ, "TICKETS_DB_PATH": str(TEST_DB)},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = [t.name for t in (await session.list_tools()).tools]
            print("Tools exposed:", tools)
            forbidden = {"approve", "assign", "complete", "reject", "delete"}
            assert not any(w in t for t in tools for w in forbidden), "forbidden tool exposed"

            print("\n===== Happy path =====")
            await call(session, "list_services", {})
            await call(session, "find_service", {"category": "pothole"})
            pc = await call(session, "lookup_postcode", {"postcode": "SO17 1BJ"})
            await call(session, "find_nearby_tickets", {"lat": 50.9265, "lng": -1.3925, "category": "pothole"})
            lat, lng = (pc["lat"], pc["lng"]) if isinstance(pc, dict) and pc.get("ok") else (50.9358, -1.3963)
            t = await call(session, "create_ticket", {
                "phone": PHONE, "category": "fly_tipping",
                "summary": "Mattress and bags dumped in the alley behind the shops",
                "location_text": "Alley behind 120 Portswood Road", "urgency": 2,
                "postcode": "SO17 1BJ", "lat": lat, "lng": lng})
            ref = t["ref_code"]
            await call(session, "propose_action", {
                "ref_code": ref, "team": "Street cleansing", "priority": 2,
                "note": "Collect fly-tipped mattress and bags; no hazardous items reported."})
            await call(session, "get_ticket_status", {"ref_code": ref})

            print("\n===== Rejection cases =====")
            await call(session, "find_service", {"category": "gas_leak"}, expect_error=True)
            await call(session, "create_ticket", {
                "phone": PHONE, "category": "gas_leak", "summary": "Smell of gas",
                "location_text": "Burgess Road", "urgency": 1}, expect_error=True)
            await call(session, "create_ticket", {
                "phone": PHONE, "category": "pothole", "summary": "Pothole somewhere",
                "location_text": "   ", "urgency": 2}, expect_error=True)
            await call(session, "propose_action", {
                "ref_code": ref, "team": "Street cleansing", "priority": 1,
                "note": "second proposal"}, expect_error=True)  # now PENDING_APPROVAL
            await call(session, "get_ticket_status", {"ref_code": "SOT-NOPE1"}, expect_error=True)
            await call(session, "lookup_postcode", {"postcode": "SW1A 1AA"})  # valid, but not Southampton
            await call(session, "lookup_postcode", {"postcode": "NOTAPOSTCODE"})

    print(f"\n{sum(results)}/{len(results)} checks passed")
    sys.exit(0 if all(results) else 1)


asyncio.run(main())

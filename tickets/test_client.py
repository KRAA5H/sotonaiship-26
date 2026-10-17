"""End-to-end test: starts server.py as a real MCP server over stdio and calls
every tool, including the cases that must be rejected.

Uses throwaway databases (test_tickets.db, test_kerbside.db) so the live ones are untouched.
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
TEST_WEB_DB = HERE / "test_kerbside.db"  # throwaway copy of the website database
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
    for f in [*HERE.glob("test_tickets.db*"), *HERE.glob("test_kerbside.db*")]:
        f.unlink()
    params = StdioServerParameters(
        command=sys.executable, args=[str(HERE / "server.py")],
        env={**os.environ, "TICKETS_DB_PATH": str(TEST_DB), "DB_PATH": str(TEST_WEB_DB)},
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
            # A pothole from the website's synthetic reports (no coordinates: matched on street text)
            await call(session, "find_nearby_tickets", {"category": "pothole", "location_text": "46 Portswood Road"})
            lat, lng = (pc["lat"], pc["lng"]) if isinstance(pc, dict) and pc.get("ok") else (50.9358, -1.3963)
            t = await call(session, "create_ticket", {
                "phone": PHONE, "category": "fly_tipping",
                "summary": "Mattress and bags dumped in the alley behind the shops",
                "location_text": "Alley behind 120 Portswood Road", "urgency": 2,
                "postcode": "SO17 1BJ", "lat": lat, "lng": lng})
            ref = t["ref_code"]
            assert t["tracking_link"] and "/r/" in t["tracking_link"], "no resident link"
            assert not t["already_reported"], "fresh complaint wrongly treated as a repeat"

            print("\n===== No repeated complaints =====")
            again = await call(session, "create_ticket", {
                "phone": PHONE, "category": "fly_tipping", "summary": "Still there",
                "location_text": "Alley behind 120 Portswood Road", "urgency": 2, "lat": lat, "lng": lng})
            results.append(again["already_reported"] and again["ref_code"] == ref)
            print(f"{'PASS' if results[-1] else 'FAIL'}  same resident again -> same ticket, nothing new")
            other = await call(session, "create_ticket", {
                "phone": "+447700900456", "category": "fly_tipping", "summary": "Mattress in the alley",
                "location_text": "alley behind 120 portswood road", "urgency": 2})
            results.append(other["duplicate_of"] == ref and not other["already_reported"])
            print(f"{'PASS' if results[-1] else 'FAIL'}  another resident -> own ticket, linked to {ref}")

            print("\n===== Officer flow =====")
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

    for f in [*HERE.glob("test_tickets.db*"), *HERE.glob("test_kerbside.db*")]:
        f.unlink(missing_ok=True)
    print(f"\n{sum(results)}/{len(results)} checks passed")
    sys.exit(0 if all(results) else 1)


asyncio.run(main())

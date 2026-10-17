#!/usr/bin/env python3
"""Fetch the no-key data sources named in the SotonShip 2026 track briefs.

Standard library only, so it runs on a fresh machine with no install:

    python fetch_sources.py

Writes each response to data/raw/ and appends a manifest entry with the URL,
timestamp, byte count and sha256, so the README can state exactly when each
number was collected (the briefs require source and date to be visible).

Sources that need an API key are listed in sources.md instead of fetched here,
on purpose: nothing in this repo should require a secret to run.

Licences: Environment Agency data is Open Government Licence v3.
postcodes.io is OGL v3. The OFSI consolidated list is published as open data.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent / "raw"
MANIFEST = OUT / "MANIFEST.json"

# Southampton city centre, and the venue postcode.
SOUTHAMPTON = (50.9025, -1.4044)

HEADERS = {"User-Agent": "sotonship2026-hack/1.0 (student hackathon project)"}


def slug(url: str) -> str:
    keep = [c if c.isalnum() else "-" for c in url.split("://", 1)[-1]]
    return "".join(keep).strip("-").replace("--", "-")[:110]


def fetch_via_curl(url: str, timeout: int) -> tuple[int, bytes, str]:
    """Second transport: curl uses the OS trust store (Schannel on Windows).

    Python's own bundle lives in the interpreter and can miss a corporate or
    campus TLS-inspecting root that the operating system already trusts. curl is
    still verifying the chain here: there is no -k anywhere.
    """
    exe = shutil.which("curl")
    if not exe:
        raise RuntimeError("curl not on PATH")
    proc = subprocess.run(
        [exe, "-sSL", "--max-time", str(timeout), "-w", "\n%{http_code} %{content_type}", url],
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", "replace").strip()[:200])
    body, _, meta = proc.stdout.rpartition(b"\n")
    code_str, _, ctype = meta.decode("utf-8", "replace").partition(" ")
    return int(code_str or 0), body, ctype.strip()


def fetch(url: str, *, timeout: int = 45) -> dict:
    """GET a URL, save the body, return a manifest entry (never raises)."""
    entry: dict = {"url": url, "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    req = urllib.request.Request(url, headers=HEADERS)
    status = ctype = None
    body = b""
    transport = "urllib"
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            status = resp.status
            ctype = resp.headers.get("Content-Type", "")
    except Exception as exc:  # noqa: BLE001 - deliberate fallback, report and continue
        first_error = f"{type(exc).__name__}: {exc}"
        try:
            status, body, ctype = fetch_via_curl(url, timeout)
            transport = "curl"
            entry["first_transport_error"] = first_error
        except Exception as exc2:  # noqa: BLE001
            entry.update(status=None, bytes=0, error=f"{first_error} | curl: {exc2}")
            return entry

    entry.update(status=status, content_type=ctype or "", transport=transport)
    if not body:
        entry.update(bytes=0, error="empty body")
        return entry

    name = slug(url)
    suffix = ".csv" if "csv" in (ctype or "") else ".json"
    path = OUT / f"{name}{suffix}"
    path.write_bytes(body)
    entry.update(bytes=len(body), sha256=hashlib.sha256(body).hexdigest(), file=str(path.name))
    return entry


def build_targets() -> list[str]:
    lat, lon = SOUTHAMPTON
    ea = "https://environment.data.gov.uk/flood-monitoring"
    return [
        # Southampton City: live flood warnings and the river/tide gauge network
        f"{ea}/id/floods?county=Hampshire",
        f"{ea}/id/floodAreas?lat={lat}&long={lon}&dist=10",
        f"{ea}/id/stations?lat={lat}&long={lon}&dist=10",
        f"{ea}/id/stations?type=TideGauge&lat={lat}&long={lon}&dist=25",
        # Geocoding, free and keyless
        "https://api.postcodes.io/postcodes/SO147SJ",
        # FinTech: the OFSI consolidated sanctions list, direct download
        "https://ofsistorage.blob.core.windows.net/publishlive/2022format/ConList.csv",
    ]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {"runs": []}
    run = {"started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "entries": []}

    ok = 0
    for url in build_targets():
        entry = fetch(url)
        state = "ok " if entry.get("status") == 200 and entry.get("bytes") else "FAIL"
        print(f"{state} {entry.get('status')} {entry.get('bytes', 0):>9} B  {url}")
        if entry.get("error"):
            print(f"     {entry['error']}")
        ok += state == "ok "
        run["entries"].append(entry)
        time.sleep(0.4)  # be polite to public APIs

    run["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    run["ok"] = ok
    run["total"] = len(build_targets())
    manifest["runs"].append(run)
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")

    print(f"\n{ok}/{run['total']} sources fetched. Manifest: {MANIFEST}")
    print("Vapor trail for the README: quote fetched_at and the source licence per file.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

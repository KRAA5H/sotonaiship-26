"""Chromeflow adapter seam.

Chromeflow is not installed in this environment. There is no bridge binary, tool or
local HTTP API to call, so this module does not invent one. When a bridge is present,
set CHROMEFLOW_URL and implement the two calls below against its documented API.

The task page already has the official form URL. Until the bridge exists, the
resident or operator can open that URL and fill the form by hand. The agent records
the prepared task and never claims a submission.
"""

import os


def status():
    url = (os.getenv("CHROMEFLOW_URL") or "").strip()
    if not url:
        return {
            "available": False,
            "reason": "Chromeflow bridge is not installed. Set CHROMEFLOW_URL when it is.",
        }
    return {"available": True, "url": url}


def open_form(url, fields=None, task_id=None):
    """Open and fill a real form through Chromeflow when the bridge exists."""
    current = status()
    if not current["available"]:
        return {"ok": False, "error": current["reason"], "task_id": task_id,
                "url": url}
    # The bridge API is intentionally not guessed. A real implementation must
    # follow the installed Chromeflow version's documented endpoint.
    return {
        "ok": False,
        "error": "Chromeflow bridge URL is set but this adapter has no documented "
                 "fill endpoint to call. Do not fake a submission.",
        "task_id": task_id,
        "url": url,
    }

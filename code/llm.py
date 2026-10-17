"""One-shot model call over any OpenAI-compatible endpoint.

No history, no session, no state: exactly one system message and one user
message per call. Falls back to a deterministic stub when no key is set, so
the loop keeps working and every caller can say which mode answered.
"""

import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

BASE_URL = (os.getenv("LLM_BASE_URL") or "https://openrouter.ai/api/v1").rstrip("/")
MODEL = os.getenv("LLM_MODEL") or "openrouter/free"
TIMEOUT = 20

STUB_REPLY = (
    "Thanks, that is logged. A crew will take a look and you will get an update here."
)


def _headers(key):
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        # OpenRouter attribution headers, ignored by other providers.
        "HTTP-Referer": "https://github.com/KRAA5H/sotonaiship-26",
        "X-Title": "Kerbside",
    }


def chat(system, user):
    """Return (reply_text, mode) where mode is 'model' or 'stub'."""
    key = (os.getenv("LLM_API_KEY") or "").strip()
    if not key:
        return STUB_REPLY, "stub"

    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": 300,
    }

    last_error = None
    for attempt in (1, 2):
        try:
            response = requests.post(
                f"{BASE_URL}/chat/completions",
                headers=_headers(key),
                json=body,
                timeout=TIMEOUT,
            )
        except requests.RequestException as error:
            last_error = f"transport error: {error}"
        else:
            if response.status_code in (429, 502) and attempt == 1:
                last_error = f"{response.status_code}: {response.text[:200]}"
                time.sleep(1.5)
                continue
            if response.status_code == 401:
                raise RuntimeError("model key rejected (401). Check LLM_API_KEY.")
            if response.status_code >= 400:
                raise RuntimeError(f"model error {response.status_code}: {response.text[:300]}")
            data = response.json()
            message = ((data.get("choices") or [{}])[0].get("message") or {})
            text = (message.get("content") or message.get("reasoning") or "").strip()
            return (text or STUB_REPLY), "model"
        time.sleep(1.5)

    raise RuntimeError(f"model call failed after retry: {last_error}")


if __name__ == "__main__":
    print(chat("Reply in one short sentence.", "there is a pothole on Weston Lane"))

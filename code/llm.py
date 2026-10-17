"""One-shot model call over any OpenAI-compatible endpoint.

No history, no session, no state: exactly one system message and one user
message per call. Falls back to a deterministic stub when no key is set or the
model returns nothing usable, so the loop keeps working and every caller can
say which mode answered.

Rule learned the hard way: reasoning traces must NEVER reach a resident. Some
models return an empty `content` with a populated `reasoning` field, and sending
that to a phone reads as a machine talking to itself.
"""

import base64
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

BASE_URL = (os.getenv("LLM_BASE_URL") or "https://openrouter.ai/api/v1").rstrip("/")
MODEL = os.getenv("LLM_MODEL") or "nvidia/nemotron-3-super-120b-a12b:free"
# Verified on a real inbound photo: reads the image and answers in about 12s.
VISION_MODEL = os.getenv("LLM_VISION_MODEL") or "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"
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


def chat(system, user, image=None):
    """Return (reply_text, mode) where mode is 'model' or 'stub'.

    `image` is (bytes, mime) from bb.download_attachment. When present the
    vision model is used and the image is sent as a data URI.

    Raises only on a configuration fault (401/400), which should fail loudly.
    Rate limits, upstream failures and empty content fall back to the stub.
    """
    key = (os.getenv("LLM_API_KEY") or "").strip()
    if not key:
        return STUB_REPLY, "stub"

    content = user
    model = MODEL
    if image:
        data, mime = image
        model = VISION_MODEL
        content = [
            {"type": "text", "text": user},
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{base64.b64encode(data).decode()}"},
            },
        ]

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ],
        "max_tokens": 300,
    }
    if image:
        # Reasoning models will otherwise spend the whole budget thinking and
        # return an empty `content`, so cap the reasoning effort and give the
        # answer room. Verified with nemotron-3.5-super-vl on a real photo.
        body["max_tokens"] = 800
        body["reasoning"] = {"effort": "low"}

    last_error = "no attempt made"
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
            time.sleep(1.5)
            continue

        if response.status_code == 401:
            raise RuntimeError("model key rejected (401). Check LLM_API_KEY.")
        if response.status_code == 400:
            raise RuntimeError(f"model rejected the request (400): {response.text[:300]}")
        if response.status_code >= 400:
            last_error = f"{response.status_code}: {response.text[:200]}"
            time.sleep(1.5)
            continue

        data = response.json()
        message = ((data.get("choices") or [{}])[0].get("message") or {})
        text = (message.get("content") or "").strip()

        if text:
            return text, "model"

        # Empty content happens when a model emits only reasoning. Never send
        # the reasoning field to a resident; retry once, then use the stub.
        last_error = "empty content (reasoning-only response)"
        if attempt == 1:
            time.sleep(1.0)

    print(f"[llm] falling back to stub: {last_error}")
    return STUB_REPLY, "stub"


if __name__ == "__main__":
    print(chat("Reply in one short sentence.", "there is a pothole on Weston Lane"))

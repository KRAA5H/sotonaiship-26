"""One-shot model call with a provider ladder.

Text goes to DeepSeek first. Photos go to a vision model on OpenRouter when
quota allows, and fall back to a text reply that asks for a description, so the
resident always gets an answer.

No history, no session, no state. Falls back to a deterministic stub when no
provider can answer, and every caller can say which mode answered.

Rule learned the hard way: reasoning traces must NEVER reach a resident. Some
models return an empty `content` with a populated `reasoning` field.
"""

import base64
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
load_dotenv(HERE.parent / ".env")   # root .env, where DEEPSEEK_API_KEY lives
load_dotenv(HERE / ".env")          # code/.env, where the OpenRouter key lives

DS_BASE = (os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com").rstrip("/")
DS_MODEL = os.getenv("DEEPSEEK_MODEL") or "deepseek-flash"

BASE_URL = (os.getenv("LLM_BASE_URL") or "https://openrouter.ai/api/v1").rstrip("/")
MODEL = os.getenv("LLM_MODEL") or "nvidia/nemotron-3-super-120b-a12b:free"
VISION_MODEL = os.getenv("LLM_VISION_MODEL") or "nvidia/nemotron-3.5-super-vl:free"

TIMEOUT = 30
STUB_REPLY = (
    "Thanks, that is logged. A crew will take a look and you will get an update here."
)
PHOTO_FALLBACK = (
    "I can't open that photo. Can you tell me in a few words what it shows and where it is?"
)


def _candidates(image):
    """Provider order for this call."""
    ds_key = (os.getenv("DEEPSEEK_API_KEY") or "").strip()
    or_key = (os.getenv("LLM_API_KEY") or "").strip()
    out = []

    if image:
        if or_key:
            out.append({"base": BASE_URL, "model": VISION_MODEL, "key": or_key,
                        "image": True, "reasoning": True})
        return out

    if ds_key:
        out.append({"base": DS_BASE, "model": DS_MODEL, "key": ds_key,
                    "image": False, "reasoning": False})
        out.append({"base": DS_BASE, "model": "deepseek-v4-pro", "key": ds_key,
                    "image": False, "reasoning": False})

    if not image and or_key:
        out.append({"base": BASE_URL, "model": MODEL, "key": or_key,
                    "image": False, "reasoning": True})
    return out


def _payload(system, user, image, candidate):
    if image and candidate["image"]:
        data, mime = image
        content = [
            {"type": "text", "text": user},
            {"type": "image_url",
             "image_url": {"url": f"data:{mime};base64,{base64.b64encode(data).decode()}"}},
        ]
    else:
        content = user

    payload = {
        "model": candidate["model"],
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ],
        "max_tokens": 300,
        "temperature": 0.7,
    }
    if candidate["reasoning"]:
        # Reasoning models spend the whole budget thinking otherwise.
        payload["max_tokens"] = 800
        payload["reasoning"] = {"effort": "low"}
    return payload


def chat(system, user, image=None):
    """Return (reply_text, mode) where mode is 'model' or 'stub'."""
    candidates = _candidates(image)
    if not candidates:
        return (PHOTO_FALLBACK if image else STUB_REPLY), "fallback"

    for candidate in candidates:
        for attempt in (1, 2):
            try:
                response = requests.post(
                    candidate["base"] + "/chat/completions",
                    headers={
                        "Authorization": "Bearer " + candidate["key"],
                        "Content-Type": "application/json",
                    },
                    json=_payload(system, user, image, candidate),
                    timeout=TIMEOUT,
                )
            except requests.RequestException as error:
                print(f"[llm] {candidate['model']} transport error: {error}")
                time.sleep(1.0)
                continue

            if response.status_code in (429, 500, 502, 503) and attempt == 1:
                time.sleep(1.2)
                continue
            if response.status_code != 200:
                print(f"[llm] {candidate['model']} HTTP {response.status_code} {response.text[:100]}")
                break

            message = ((response.json().get("choices") or [{}])[0].get("message") or {})
            text = (message.get("content") or "").strip()
            if text:
                return text, "model"
            print(f"[llm] {candidate['model']} empty content")
            break

    if image:
        print("[llm] no vision provider answered, asking for a description")
        return PHOTO_FALLBACK, "fallback"
    print("[llm] no provider answered, using stub")
    return STUB_REPLY, "stub"


if __name__ == "__main__":
    print(chat("Reply in one short sentence.", "there is a pothole on Weston Lane"))

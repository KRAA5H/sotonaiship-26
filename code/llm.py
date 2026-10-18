"""One-shot model call with a provider ladder. DeepSeek first, thinking off.

DeepSeek V4.1 Flash does text and images and is the model for every call:
triage, the photo agent and the reply agent. Thinking is switched off
explicitly ("thinking": {"type": "disabled"}), because DeepSeek thinks by
default and thinking costs seconds a resident on a phone can feel.

One exception, measured on the live line: for an image DeepSeek has returned
HTTP 200 with EMPTY content when thinking was off. So an image is sent with
thinking off first, and only if that comes back empty is it retried once with
low-effort thinking. That retry is logged, so its real rate can be counted.

Fallbacks, in order: deepseek-v4-pro (text only), then an OpenRouter model,
then a fixed stub. Every caller gets (text, mode) and can say who answered.

Rule learned the hard way: reasoning traces must NEVER reach a resident. Only
`content` is ever returned.

Usage: each call appends one line to logs/llm_usage.jsonl with the model, the
purpose, the latency and the token counts. Never the message text. That file
is how cost per report gets measured instead of estimated.
"""

import base64
import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import dotenv_values

HERE = Path(__file__).resolve().parent
PROJECT_ENV = (HERE.parent / ".env", HERE / ".env")   # root: DeepSeek key, code/: OpenRouter key

# The project's .env must win over a key already exported in the shell.
# load_dotenv never overrides, so a machine-level DEEPSEEK_API_KEY (the one the
# pi agent uses for itself) would silently pay for this project's calls instead.
# Only keys the files actually define are overridden; the rest of the process
# environment is left untouched.
_project_keys = {}
for _env_path in PROJECT_ENV:
    _project_keys.update({k: v for k, v in dotenv_values(_env_path).items() if v})
os.environ.update(_project_keys)


def key_source(name):
    """Project .env file that supplied a key, with its last four characters.

    Never the key itself: the point is to see which key is in use when two of
    them have the same name, not to put a secret in a log.
    """
    for path in PROJECT_ENV:
        if _project_keys.get(name):
            return f"{path.name} (...{_project_keys[name][-4:]})"
    return "environment"

DS_BASE = (os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com").rstrip("/")
DS_MODEL = os.getenv("DEEPSEEK_MODEL") or "deepseek-flash"

BASE_URL = (os.getenv("LLM_BASE_URL") or "https://openrouter.ai/api/v1").rstrip("/")
MODEL = os.getenv("LLM_MODEL") or "nvidia/nemotron-3-super-120b-a12b:free"
VISION_MODEL = os.getenv("LLM_VISION_MODEL") or "nvidia/nemotron-3.5-super-vl:free"

# Seconds. A resident is waiting on a phone; a slow provider is skipped, not waited for.
TIMEOUT = float(os.getenv("LLM_TIMEOUT") or "15")
RETRY_PAUSE = 0.3
USAGE_LOG = Path(os.getenv("LLM_USAGE_LOG") or (HERE / "logs" / "llm_usage.jsonl"))

STUB_REPLY = (
    "Thanks, that is logged. A crew will take a look and you will get an update here."
)
PHOTO_FALLBACK = (
    "I can't open that photo. Can you tell me in a few words what it shows and where it is?"
)

_usage_lock = threading.Lock()


def _candidates(image):
    """Provider order for this call. DeepSeek never thinks unless an image comes back empty."""
    ds_key = (os.getenv("DEEPSEEK_API_KEY") or "").strip()
    or_key = (os.getenv("LLM_API_KEY") or "").strip()
    out = []

    if image:
        if ds_key:
            out.append({"base": DS_BASE, "model": DS_MODEL, "key": ds_key,
                        "image": True, "thinking": False, "provider": "deepseek"})
            # Only reached when the thinking-off call returned empty content.
            out.append({"base": DS_BASE, "model": DS_MODEL, "key": ds_key,
                        "image": True, "thinking": True, "provider": "deepseek",
                        "only_after_empty": True})
        if or_key:
            out.append({"base": BASE_URL, "model": VISION_MODEL, "key": or_key,
                        "image": True, "thinking": True, "provider": "openrouter"})
        return out

    if ds_key:
        out.append({"base": DS_BASE, "model": DS_MODEL, "key": ds_key,
                    "image": False, "thinking": False, "provider": "deepseek"})
        out.append({"base": DS_BASE, "model": "deepseek-v4-pro", "key": ds_key,
                    "image": False, "thinking": False, "provider": "deepseek"})
    if or_key:
        out.append({"base": BASE_URL, "model": MODEL, "key": or_key,
                    "image": False, "thinking": True, "provider": "openrouter"})
    return out


def _payload(system, user, image, candidate, max_tokens=None, temperature=None):
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
        "max_tokens": max_tokens or 300,
        "temperature": 0.7 if temperature is None else temperature,
    }
    if candidate["provider"] == "deepseek":
        if candidate["thinking"]:
            # The empty-image retry only: short thinking, with room left for the answer.
            payload["thinking"] = {"type": "enabled"}
            payload["reasoning_effort"] = "low"
            payload["max_tokens"] = max(payload["max_tokens"], 600)
        else:
            payload["thinking"] = {"type": "disabled"}
    elif candidate["thinking"]:
        # OpenRouter's free fallbacks are reasoning models: keep it short.
        payload["max_tokens"] = max(payload["max_tokens"], 400)
        payload["reasoning"] = {"effort": "low", "exclude": True}
    return payload


def _log_usage(candidate, purpose, started, status, data):
    """One line per call: model, purpose, latency and tokens. Never the text."""
    usage = (data or {}).get("usage") or {}
    line = {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provider": candidate["provider"],
        "model": candidate["model"],
        "thinking": candidate["thinking"],
        "purpose": purpose or "",
        "status": status,
        "ms": round((time.time() - started) * 1000),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "cache_hit_tokens": usage.get("prompt_cache_hit_tokens"),
    }
    try:
        with _usage_lock:
            USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
            with USAGE_LOG.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(line) + "\n")
    except OSError:
        pass  # a full disk must never stop a reply
    return line


def chat(system, user, image=None, max_tokens=None, temperature=None, timeout=None, purpose=None):
    """Return (reply_text, mode) where mode is 'model', 'stub' or 'fallback'."""
    candidates = _candidates(image)
    if not candidates:
        return (PHOTO_FALLBACK if image else STUB_REPLY), "fallback"

    empty_image = False
    for candidate in candidates:
        if candidate.get("only_after_empty") and not empty_image:
            continue
        for attempt in (1, 2):
            started = time.time()
            try:
                response = requests.post(
                    candidate["base"] + "/chat/completions",
                    headers={
                        "Authorization": "Bearer " + candidate["key"],
                        "Content-Type": "application/json",
                    },
                    json=_payload(system, user, image, candidate, max_tokens, temperature),
                    timeout=timeout or TIMEOUT,
                )
            except requests.RequestException as error:
                print(f"[llm] {candidate['model']} transport error: {error}")
                _log_usage(candidate, purpose, started, "transport_error", None)
                break  # a timeout already cost the resident seconds: next provider

            if response.status_code in (429, 500, 502, 503) and attempt == 1:
                _log_usage(candidate, purpose, started, response.status_code, None)
                time.sleep(RETRY_PAUSE)
                continue
            if response.status_code != 200:
                print(f"[llm] {candidate['model']} HTTP {response.status_code} {response.text[:100]}")
                _log_usage(candidate, purpose, started, response.status_code, None)
                break

            data = response.json()
            line = _log_usage(candidate, purpose, started, 200, data)
            message = ((data.get("choices") or [{}])[0].get("message") or {})
            text = (message.get("content") or "").strip()
            if text:
                if candidate["thinking"] and candidate["provider"] == "deepseek":
                    print(f"[llm] image answered only with thinking on ({line['ms']} ms)")
                return text, "model"
            if image and candidate["provider"] == "deepseek" and not candidate["thinking"]:
                print("[llm] image came back empty with thinking off, retrying with low thinking")
                empty_image = True
                break
            # An empty text reply: one quick retry usually answers.
            if attempt == 1:
                time.sleep(RETRY_PAUSE)
                continue
            print(f"[llm] {candidate['model']} empty content twice")
            break

    if image:
        print("[llm] no vision provider answered, asking for a description")
        return PHOTO_FALLBACK, "fallback"
    print("[llm] no provider answered, using stub")
    return STUB_REPLY, "stub"


if __name__ == "__main__":
    print(chat("Reply in one short sentence.", "there is a pothole on Weston Lane", purpose="cli"))

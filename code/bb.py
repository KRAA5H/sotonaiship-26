"""Minimal BlueBubbles client.

One place that knows the URLs, the auth parameter and the payload quirks.
Every call prints its status and response body: silent failures are what eat
hackathon nights.

Verified against server 1.9.9 with private_api disabled:
  - GET  /api/v1/ping            works
  - POST /api/v1/chat/query      works (GET /api/v1/chat is 404 on this build)
  - chat GUIDs look like any;-;<address>, do not hardcode iMessage;-;
  - method must be apple-script while private_api is false
"""

import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

BASE = (os.getenv("BLUEBUBBLES_SERVER_URL") or "").rstrip("/")
PASSWORD = os.getenv("BLUEBUBBLES_PASSWORD") or ""
METHOD = os.getenv("BLUEBUBBLES_METHOD") or "apple-script"
TIMEOUT = 10


def _short(obj, limit=400):
    try:
        return json.dumps(obj, ensure_ascii=True)[:limit]
    except (TypeError, ValueError):
        return str(obj)[:limit]


def _call(http_method, path, params=None, payload=None, timeout=None):
    """Single HTTP call. Returns (status_code, parsed_body).

    Transport failures return status 0 instead of raising, so a slow AppleScript
    path cannot turn into a traceback in the middle of a demo.
    """
    if not BASE:
        raise RuntimeError("BLUEBUBBLES_SERVER_URL is not set")
    query = {"password": PASSWORD}
    if params:
        query.update(params)
    try:
        response = requests.request(
            http_method,
            f"{BASE}{path}",
            params=query,
            json=payload,
            timeout=timeout or TIMEOUT,
        )
    except requests.RequestException as error:
        print(f"[bb] {http_method} {path} -> transport error: {error}")
        return 0, {"error": str(error)}
    try:
        body = response.json()
    except ValueError:
        body = {"raw": response.text[:400]}
    print(f"[bb] {http_method} {path} -> {response.status_code} {_short(body, 300)}")
    return response.status_code, body


def ping():
    return _call("GET", "/api/v1/ping")


def server_info():
    return _call("GET", "/api/v1/server/info")


def list_chats(limit=50):
    """POST /chat/query, because GET /chat is 404 on this build."""
    code, body = _call(
        "POST",
        "/api/v1/chat/query",
        payload={"limit": limit, "offset": 0, "with": ["lastmessage", "participants"]},
    )
    return code, (body.get("data") or [])


def find_chat(address):
    """Return the chat GUID for an address, or None."""
    address = (address or "").strip().lower()
    code, chats = list_chats()
    for chat in chats:
        participants = [((p or {}).get("address") or "").lower() for p in (chat.get("participants") or [])]
        if address and address in participants:
            return chat.get("guid")
        if address and (chat.get("guid") or "").lower().endswith(f";-;{address}"):
            return chat.get("guid")
    return None


def create_chat(address, text=None):
    """Create an iMessage chat. macOS Big Sur and later require a first message.

    Verified on server 1.9.9 / macOS 26.5: omitting `message` returns
    500 "A message is required when creating chats on macOS Big Sur or newer!"
    """
    payload = {"addresses": [address], "service": "iMessage"}
    payload["message"] = text or "kerbside test"
    # Chat creation goes through AppleScript and routinely takes longer than
    # a plain send: the 10s default timed out on this server while the chat was
    # still created successfully. Allow 45s here.
    code, body = _call("POST", "/api/v1/chat/new", payload=payload, timeout=45)
    if code >= 400:
        return None
    return (body.get("data") or {}).get("guid")


def ensure_chat(address, text=None):
    """Return (chat_guid, already_sent). If no chat exists, create it with
    `text` as the first message, so the caller must not send it again."""
    guid = find_chat(address)
    if guid:
        return guid, False
    return create_chat(address, text), True


def send_text(chat_guid, text, method=None):
    """Send a message. Tries `message`, then `text`, on a payload-shaped 4xx.

    Verified on server 1.9.9: the `message` field is accepted and returns 200.
    Field naming differs between the docs' Python sample (`text`) and community
    payloads (`message`), so the fallback stays. Never retry on 401/403:
    a wrong password should fail loudly and once.
    """
    payload = {
        "chatGuid": chat_guid,
        "tempGuid": f"kerbside-{int(time.time() * 1000)}",
        "message": text,
        "method": method or METHOD,
    }
    code, body = _call("POST", "/api/v1/message/text", payload=payload)
    if code in (400, 422):
        payload.pop("message", None)
        payload["text"] = text
        code, body = _call("POST", "/api/v1/message/text", payload=payload)
    ok = code < 400
    if ok:
        print(f"[bb] sent to {chat_guid}: {text.encode('ascii', 'backslashreplace').decode()}")
    return ok, body


def normalise(payload):
    """Turn a BlueBubbles webhook body into a plain dict, or None to ignore."""
    if (payload or {}).get("type") != "new-message":
        return None
    data = payload.get("data") or {}
    if data.get("isFromMe"):
        return None
    chats = data.get("chats") or []
    if not chats:
        return None
    return {
        "chat_guid": chats[0].get("guid"),
        "sender": ((data.get("handle") or {}).get("address") or ""),
        "text": (data.get("text") or "").strip(),
        "attachments": data.get("attachments") or [],
        "message_guid": data.get("guid"),
        "date_created": data.get("dateCreated"),
    }


_self_address = None


def self_address():
    """The server's own iMessage address, cached. Used to break self-chat loops."""
    global _self_address
    if _self_address is None:
        code, body = _call("GET", "/api/v1/server/info")
        _self_address = ((body or {}).get("data") or {}).get("detected_imessage") or ""
    return _self_address

# Send iMessage, then OpenRouter reply

One-shot build. No database, no session, no classification.

## Confirmed by request

| Thing | Value |
|---|---|
| BlueBubbles | `http://192.168.0.26:1234`, ping 200, server 1.9.9, `private_api: false` so method is `apple-script` |
| Chat list | `GET /api/v1/chat` is 404. Use `POST /api/v1/chat/query` |
| GUIDs | `any;-;<address>`, never hardcode `iMessage;-;` |
| Existing chats | `any;-;anirudh.udupi@gmail.com`, `any;-;+13478193890` |
| OpenRouter | key works. `openrouter/free` costs 0, takes text and images, 200k context, test returned `ok` |
| This machine | Windows `192.168.0.202`, hosts Flask on 5005 for the webhook |

## Files

**New:** `code/bb.py`, `code/send_test.py`, `code/llm.py`, `code/echo_ai.py`, `code/.env.example`, `code/requirements.txt`

**Edit:** `code/blue_bubbles.py` only (import `bb`, add `MODE=echo`, `host="0.0.0.0"`). Delete its local `send_reply()` and reuse `bb.send_text()`.

**Untouched:** `conversational_ai.py`, `database.py`, root duplicates, `code/data/`.

## Steps

- [x] `.env`: URL, password, `BLUEBUBBLES_METHOD=apple-script`, `LLM_BASE_URL=https://openrouter.ai/api/v1`, `LLM_MODEL=openrouter/free`, key
- [x] `bb.py`: `ping`, `find_chat`, `create_chat`, `send_text`. Try `message` then `text` on 4xx. Print status and body every call
- [x] `send_test.py --ping / --chats / --to / --text`
- [x] Send to `anirudh.udupi@gmail.com` and confirm on their device
- [x] `llm.py`: POST `/chat/completions`, 20s timeout, retry once on 429 or 502, stub reply when no key
- [x] `echo_ai.py "there is a pothole on Weston Lane"`, prints reply, latency, mode
- [x] `MODE=echo` in the webhook: ignore `isFromMe`, one call, one reply, return 200
- [x] Point BlueBubbles webhook at `http://192.168.0.202:5005/webhook`
- [ ] Inbound test from a **different** account, because a message from the Mac's own address arrives as `isFromMe` and is correctly ignored

## Verify

| Command | Expect |
|---|---|
| `python code/send_test.py --ping` | 200, version 1.9.9 |
| `python code/send_test.py --chats` | Two GUIDs |
| `python code/send_test.py --to "anirudh.udupi@gmail.com" --text "test"` | 200 and the message arrives |
| `python code/echo_ai.py "pothole on Weston Lane"` | Model reply, latency, `mode=model` |
| Text the number from another phone | Webhook logs it, reply arrives. **Not yet done: needs a second phone or account** |

Stage 1 is done when a phone buzzes. Nothing else counts.

## Notes

- The key and the password live in `.env` only. Never in markdown, never committed. Rotate if they leak.
- `openrouter/free` is a router, so the backing model varies and it can return 429 or 502. Retry once, then fall back to the stub and say so.
- Vision works on `openrouter/free`. Wiring photos is the next task, not this one.

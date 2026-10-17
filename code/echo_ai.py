"""Stage 2 CLI: one message in, one model call, one reply out.

No context is sent. This is deliberately the dumbest possible link between the
model and the channel, so we can prove the pipe before adding anything.

Usage:
  python code/echo_ai.py "there is a pothole on Weston Lane"
  python code/echo_ai.py "there is a pothole on Weston Lane" --send --to "someone@example.com"
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bb
import llm

SYSTEM = (
    "You are the street report line for Southampton City Council. "
    "Reply in at most two short sentences, in plain English, with no jargon. "
    "Never give safety advice; if life is at risk, tell the person to call 999."
)


def main():
    parser = argparse.ArgumentParser(description="One-shot model reply")
    parser.add_argument("text", nargs="+", help="the resident's message")
    parser.add_argument("--send", action="store_true", help="send the reply through BlueBubbles")
    parser.add_argument("--to", help="recipient address, used with --send")
    parser.add_argument("--chat", help="existing chat GUID, used with --send")
    args = parser.parse_args()

    message = " ".join(args.text)
    started = time.time()
    reply, mode = llm.chat(SYSTEM, message)
    elapsed = time.time() - started

    print("in :", message.encode("ascii", "backslashreplace").decode())
    print("out:", reply.encode("ascii", "backslashreplace").decode())
    print(f"mode: {mode} | {elapsed:.2f}s | model: {llm.MODEL}")

    if args.send:
        if args.chat:
            guid, already_sent = args.chat, False
        elif args.to:
            guid, already_sent = bb.ensure_chat(args.to, reply)
        else:
            guid, already_sent = None, False
        if not guid:
            print("no chat to send to, pass --to or --chat")
            return 1
        if already_sent:
            print("chat created, reply sent as the first message")
            return 0
        ok, body = bb.send_text(guid, reply)
        if not ok:
            print("send failed:", body)
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

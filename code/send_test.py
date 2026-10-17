"""Stage 1 CLI: prove we can talk to BlueBubbles and send an iMessage.

Usage:
  python code/send_test.py --ping
  python code/send_test.py --chats
  python code/send_test.py --info
  python code/send_test.py --to "someone@example.com" --text "kerbside test"
  python code/send_test.py --chat "any;-;someone@example.com" --text "kerbside test"
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bb


def safe(text):
    return str(text).encode("ascii", "backslashreplace").decode()


def main():
    parser = argparse.ArgumentParser(description="BlueBubbles send test")
    parser.add_argument("--ping", action="store_true", help="check the server is reachable")
    parser.add_argument("--info", action="store_true", help="server version and account details")
    parser.add_argument("--chats", action="store_true", help="list existing chats and GUIDs")
    parser.add_argument("--to", help="recipient address, chat is found or created")
    parser.add_argument("--chat", help="existing chat GUID")
    parser.add_argument("--text", default="kerbside test", help="message body")
    args = parser.parse_args()

    if not any([args.ping, args.info, args.chats, args.to, args.chat]):
        parser.print_help()
        return 1

    if args.ping:
        code, body = bb.ping()
        print("server reachable" if code == 200 else f"ping failed: {code}")
        if code != 200:
            return 1

    if args.info:
        code, body = bb.server_info()
        data = (body or {}).get("data") or {}
        print(
            "version", data.get("server_version"),
            "| private_api", data.get("private_api"),
            "| imessage", data.get("detected_imessage"),
        )

    if args.chats:
        code, chats = bb.list_chats()
        print(f"{len(chats)} chats")
        for chat in chats:
            people = [((p or {}).get("address") or "") for p in (chat.get("participants") or [])]
            print(" ", chat.get("guid"), "|", chat.get("displayName") or ", ".join(people))

    if args.to or args.chat:
        if args.to:
            guid, already_sent = bb.ensure_chat(args.to, args.text)
        else:
            guid, already_sent = args.chat, False
        if not guid:
            print("could not find or create a chat for", args.to)
            return 1
        print("chat:", guid)
        print("sending:", safe(args.text))
        if already_sent:
            print("chat created, first message sent as part of creation")
            return 0
        ok, body = bb.send_text(guid, args.text)
        if not ok:
            print("send failed:", safe(body))
            return 1
        print("sent ok")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

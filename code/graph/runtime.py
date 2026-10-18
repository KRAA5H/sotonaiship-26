"""The graph runtime: one compiled graph, one thread key, one checkpointer.

Step 6 has no model call, no report write and no delivery. `--turn` shows the
capture draft; `--selftest` proves the thread and the cheap and danger edges.
"""

import argparse
import json
import sys
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from langgraph.checkpoint.memory import MemorySaver  # noqa: E402
from langgraph.checkpoint.sqlite import SqliteSaver  # noqa: E402

import messages  # noqa: E402
import tools  # noqa: E402
import llm as llm_module  # noqa: E402
from graph import execution, store, writer  # noqa: E402
from graph.build import build_graph  # noqa: E402
from graph.nodes import danger, wants_greeting  # noqa: E402


def _now():
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Deps:
    threads: object
    playbooks: dict
    llm: object | None = None
    now: Callable[[], datetime] = _now
    notifier: object | None = None
    reports: object | None = None
    outbox: object | None = None
    ops: object | None = None
    claims: object | None = None
    profiles: object | None = None
    tasks: object | None = None
    council: object | None = None
    writer: bool = True


def load_playbooks(path=None):
    target = (Path(path) if path else
              Path(__file__).resolve().parents[1] / "services" / "playbooks" / "_index.json")
    return json.loads(target.read_text(encoding="utf-8"))


def _council_store(db):
    from council.store import CouncilStore
    return CouncilStore(db)


class TurnRuntime:
    def __init__(self, deps, checkpointer=None):
        self.deps = deps
        self.graph = build_graph(deps, checkpointer if checkpointer is not None else MemorySaver())

    def turn(self, inbound):
        sender = inbound.get("sender") or ""
        thread_id = tools.reporter_ref(sender) or "h-anon"
        turn_id = inbound.get("message_guid") or uuid.uuid4().hex
        before = self.deps.threads.load(thread_id)
        duplicate = bool(before and before.get("last_turn_id") == turn_id)
        initial = {"thread_id": thread_id, "turn_id": turn_id, "inbound": inbound}
        config = {"configurable": {"thread_id": thread_id}}
        state = self.graph.invoke(initial, config)
        kind = self._kind(state, inbound, duplicate)
        if kind != "duplicate":
            self.deps.threads.save(
                thread_id,
                last_turn_id=turn_id,
                active_incident_id=state.get("active_incident_id"),
                incident_draft=state.get("incident_draft"),
                pending_question=state.get("pending_question"),
                last_claims=state.get("last_claims_sent"),
                last_action=(state.get("executed_outcome") or {}).get("action"),
            )
        plan = state.get("bubble_plan") or {}
        if kind != "duplicate" and getattr(self.deps, "profiles", None):
            profile = state.get("profile") or {}
            if not profile.get("style") and (inbound.get("text") or "").strip():
                style = writer._register(inbound.get("text") or "")
                self.deps.profiles.save(thread_id, style=style)
                state["profile"] = {**profile, "style": style}
        if kind == "greeting" and self.deps.writer and self.deps.llm is not None:
            greeting_outcome = {"action": "answer", "saved": False, "facts": [],
                                "missing": [], "destination": None, "status": None,
                                "duplicate_of": None}
            written = writer.write(state, self.deps, greeting_outcome,
                                   execution.context(self.deps, state))
            plan = written or {"bubbles": [], "url": None, "source_url": None,
                               "suppressed": True}
        if not plan.get("bubbles") and kind in ("emergency", "threat"):
            copy = {"emergency": messages.emergency, "threat": messages.threat}[kind]()
            plan = {"bubbles": [{"purpose": "action", "text": line}
                                for line in copy.splitlines() if line.strip()],
                    "url": None, "source_url": None, "suppressed": False}
        if kind != "duplicate" and hasattr(self.deps.threads, "append"):
            try:
                self.deps.threads.append(thread_id, "resident",
                                         inbound.get("text") or "(photo)",
                                         self.deps.now().isoformat(timespec="seconds"))
                for bubble in plan.get("bubbles") or []:
                    self.deps.threads.append(thread_id, "agent", bubble.get("text") or "",
                                             self.deps.now().isoformat(timespec="seconds"))
            except Exception as error:  # noqa: BLE001 - history must not break the reply
                print(f"[history] could not save the conversation: {error}")
        return {
            "thread_id": thread_id,
            "turn_id": turn_id,
            "kind": kind,
            "bubbles": [item.get("text") for item in plan.get("bubbles") or []],
            "url": plan.get("url"),
            "source_url": plan.get("source_url"),
            "state": state,
        }

    @staticmethod
    def _kind(state, inbound, duplicate):
        if duplicate:
            return "duplicate"
        if state.get("emergency"):
            return "emergency"
        text = inbound.get("text") or ""
        if state.get("short_circuit"):
            if wants_greeting(text):
                return "greeting"
            return danger(text) or "short_circuit"
        if state.get("suppressed"):
            ref = inbound.get("photo_ref") or inbound.get("image_ref")
            return "empty" if not text.strip() and not ref else "silence"
        outcome = state.get("executed_outcome") or {}
        if outcome.get("saved"):
            return "saved"
        return {"ask": "asked", "answer": "answered", "escalate": "escalated"}.get(
            outcome.get("action"), "handled")


def selftest():
    """Run the shell on a temp database. Returns one line per turn."""
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "kerbside.db"
        store.migrate(db)
        deps = Deps(threads=store.ThreadStore(db), playbooks=load_playbooks(),
                    reports=db, ops=store.TurnOperations(db), outbox=store.Outbox(db),
                    claims=store.Claims(db), profiles=store.ProfileStore(db),
                    tasks=store.TaskStore(db), council=_council_store(db))
        runtime = TurnRuntime(deps, MemorySaver())

        def turn(text, guid):
            return runtime.turn({"sender": "+447700900001", "text": text,
                                 "message_guid": guid})

        turns = [
            ("tree", turn("there is a tree fallen on the road", "g-tree")),
            ("duplicate", turn("there is a tree fallen on the road", "g-tree")),
            ("greeting", turn("hello", "g-hello")),
            ("silence", turn("thanks", "g-thanks")),
            ("emergency", turn("there is a gas leak in the kitchen", "g-emergency")),
            ("empty", turn("", "g-empty")),
        ]
        return [f"{name}: {result['kind']}" for name, result in turns]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--turn", help="run one text through the graph")
    parser.add_argument("--selftest", action="store_true", help="run the scripted turns")
    parser.add_argument("--db", default=None, help="database path (default code/graph.db)")
    args = parser.parse_args(argv)

    if args.selftest:
        for line in selftest():
            print(line)
        return 0
    if not args.turn:
        parser.error("give --turn TEXT or --selftest")

    db = Path(args.db) if args.db else Path(__file__).resolve().parents[1] / "graph.db"
    store.migrate(db)
    deps = Deps(threads=store.ThreadStore(db), playbooks=load_playbooks(), llm=llm_module,
                reports=db, ops=store.TurnOperations(db), outbox=store.Outbox(db),
                claims=store.Claims(db), profiles=store.ProfileStore(db),
                tasks=store.TaskStore(db), council=_council_store(db))
    with SqliteSaver.from_conn_string(str(db)) as saver:
        runtime = TurnRuntime(deps, saver)
        result = runtime.turn({"sender": "+447700900000", "text": args.turn,
                               "message_guid": uuid.uuid4().hex})
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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

import tools  # noqa: E402
from graph import store  # noqa: E402
from graph.build import build_graph  # noqa: E402
from graph.nodes import wants_greeting  # noqa: E402


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


def load_playbooks(path=None):
    target = (Path(path) if path else
              Path(__file__).resolve().parents[1] / "services" / "playbooks" / "_index.json")
    return json.loads(target.read_text(encoding="utf-8"))


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
        self.deps.threads.save(
            thread_id,
            last_turn_id=turn_id,
            incident_draft=state.get("incident_draft"),
            pending_question=state.get("pending_question"),
            last_claims=state.get("last_claims_sent"),
        )
        return {
            "thread_id": thread_id,
            "turn_id": turn_id,
            "kind": self._kind(state, inbound, duplicate),
            "state": state,
        }

    @staticmethod
    def _kind(state, inbound, duplicate):
        if duplicate:
            return "duplicate"
        if state.get("suppressed"):
            return "suppressed"
        if state.get("emergency"):
            return "emergency"
        if state.get("short_circuit"):
            return "greeting" if wants_greeting(inbound.get("text") or "") else "short_circuit"
        return "captured"


def selftest():
    """Run the shell on a temp database. Returns one line per turn."""
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "kerbside.db"
        store.migrate(db)
        deps = Deps(threads=store.ThreadStore(db), playbooks={})
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
    deps = Deps(threads=store.ThreadStore(db), playbooks=load_playbooks())
    with SqliteSaver.from_conn_string(str(db)) as saver:
        runtime = TurnRuntime(deps, saver)
        result = runtime.turn({"sender": "+447700900000", "text": args.turn,
                               "message_guid": uuid.uuid4().hex})
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""One process-level graph runtime for the simulator and the iMessage webhook.

The thread store keeps the draft, the pending question and the claims. The
checkpointer here is in memory: a restart keeps the essentials, not the raw chat
history (D56). One writer, one runtime, one key.
"""

from langgraph.checkpoint.memory import MemorySaver

import llm
import reports_db

from . import store
from .runtime import Deps, TurnRuntime, load_playbooks

_RUNTIME = None


def _council_store(db):
    from council.store import CouncilStore
    return CouncilStore(db)


def get_runtime():
    global _RUNTIME
    if _RUNTIME is None:
        db = reports_db.DB_PATH
        store.migrate(db)
        deps = Deps(
            threads=store.ThreadStore(db),
            playbooks=load_playbooks(),
            llm=llm,
            reports=db,
            ops=store.TurnOperations(db),
            outbox=store.Outbox(db),
            claims=store.Claims(db),
            profiles=store.ProfileStore(db),
            tasks=store.TaskStore(db),
            council=_council_store(db),
        )
        _RUNTIME = TurnRuntime(deps, MemorySaver())
    return _RUNTIME

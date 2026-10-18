"""The compiled graph: one turn from hydrate to a truthful outcome.

Capture happens before any category decision. A plan is checked before it can
write, repaired once, and the fallback keeps the incident rather than dropping it.
"""

from langgraph.graph import END, START, StateGraph

from .nodes import make_nodes, route_precheck, route_validate
from .state import ThreadState


def build_graph(deps, checkpointer=None):
    nodes = make_nodes(deps)
    graph = StateGraph(ThreadState)
    for name in ("hydrate", "precheck", "capture", "decide", "validate",
                 "repair", "fallback", "execute", "compose", "lint", "enqueue"):
        graph.add_node(name, nodes[name])
    graph.add_edge(START, "hydrate")
    graph.add_edge("hydrate", "precheck")
    graph.add_conditional_edges("precheck", route_precheck,
                                {"end": END, "capture": "capture"})
    graph.add_edge("capture", "decide")
    graph.add_edge("decide", "validate")
    graph.add_edge("repair", "decide")
    graph.add_edge("fallback", "execute")
    graph.add_conditional_edges("validate", route_validate,
                                {"execute": "execute", "repair": "repair",
                                 "fallback": "fallback"})
    graph.add_edge("execute", "compose")
    graph.add_edge("compose", "lint")
    graph.add_edge("lint", "enqueue")
    graph.add_edge("enqueue", END)
    return graph.compile(checkpointer=checkpointer)

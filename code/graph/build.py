"""The compiled graph: one turn from hydrate to a truthful outcome.

Capture happens before any category decision. A plan is checked before it can
write, repaired once, and the fallback keeps the incident rather than dropping it.
"""

from langgraph.graph import END, START, StateGraph

from .nodes import make_nodes, route_cheap, route_precheck, route_validate
from .specialist_node import make_specialist_node
from .state import ThreadState


def build_graph(deps, checkpointer=None):
    nodes = make_nodes(deps)
    graph = StateGraph(ThreadState)
    for name in ("hydrate", "precheck", "cheap", "capture", "decide", "validate",
                 "repair", "fallback", "execute", "compose", "lint", "enqueue"):
        graph.add_node(name, nodes[name])
    graph.add_node("specialist", make_specialist_node(deps))
    graph.add_edge(START, "hydrate")
    graph.add_edge("hydrate", "precheck")
    graph.add_conditional_edges(
        "precheck",
        lambda state: "end" if state.get("suppressed") or state.get("emergency") else "cheap",
        {"end": END, "cheap": "cheap"})
    graph.add_conditional_edges("cheap", route_cheap,
                                {"end": END, "capture": "capture"})
    graph.add_edge("capture", "decide")
    graph.add_edge("decide", "specialist")
    graph.add_edge("specialist", "validate")
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

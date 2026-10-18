"""The compiled graph. Step 6 is the shell: hydrate, precheck, cheap, capture."""

from langgraph.graph import END, START, StateGraph

from .nodes import make_nodes, route_cheap, route_precheck
from .state import ThreadState


def build_graph(deps, checkpointer=None):
    nodes = make_nodes(deps)
    graph = StateGraph(ThreadState)
    graph.add_node("hydrate", nodes["hydrate"])
    graph.add_node("precheck", nodes["precheck"])
    graph.add_node("cheap", nodes["cheap"])
    graph.add_node("capture", nodes["capture"])
    graph.add_edge(START, "hydrate")
    graph.add_edge("hydrate", "precheck")
    graph.add_conditional_edges("precheck", route_precheck,
                                {"end": END, "cheap": "cheap"})
    graph.add_conditional_edges("cheap", route_cheap,
                                {"end": END, "capture": "capture"})
    graph.add_edge("capture", END)
    return graph.compile(checkpointer=checkpointer)

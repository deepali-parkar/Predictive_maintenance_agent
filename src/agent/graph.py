"""LangGraph assembly + runner. Falls back to an equivalent sequential runner ONLY if langgraph is not installed (logged)."""
from __future__ import annotations
from typing import Optional
from src.agent.nodes import AgentDeps, build_nodes
from src.agent.routing import TRANSITIONS
from src.agent.state import AgentState
from src.common.logging_config import get_logger, new_correlation_id, set_correlation_id

log = get_logger("graph")

def build_graph(deps: AgentDeps):
    nodes = build_nodes(deps)
    try:
        from langgraph.graph import END, StateGraph
    except ImportError:
        log.warning("langgraph not installed - using sequential fallback runner with identical transitions"); return nodes, None
    g = StateGraph(AgentState)
    for n, f in nodes.items(): g.add_node(n, f)
    g.set_entry_point("initialize")
    for n, (fn, targets) in TRANSITIONS.items(): g.add_conditional_edges(n, fn, {t: t for t in targets})
    g.add_edge("finalize", END)
    try:
        from langgraph.checkpoint.memory import MemorySaver
        return nodes, g.compile(checkpointer=MemorySaver())
    except ImportError: return nodes, g.compile()

def run_sequential(nodes: dict, state: dict) -> dict:
    cur = "initialize"
    while True:
        state = {**state, **nodes[cur](state)}
        if cur == "finalize": return state
        cur = TRANSITIONS[cur][0](state)

class SentinelAgent:
    def __init__(self, deps: AgentDeps): self.deps = deps; self.nodes, self.graph = build_graph(deps)
    def run(self, asset_id: str, risk_event_id: Optional[str] = None, user_question: str = "", correlation_id: Optional[str] = None) -> dict:
        cid = correlation_id or new_correlation_id("run"); set_correlation_id(cid)
        state = {"asset_id": asset_id, "risk_event_id": risk_event_id or "", "user_question": user_question, "correlation_id": cid}
        if self.graph is not None:
            out = self.graph.invoke(state, config={"configurable": {"thread_id": cid}})
        else: out = run_sequential(self.nodes, state)
        return out["result"]

MERMAID = """flowchart TD
  A[initialize] --> B[mcp_context]
  B --> C[evidence_preparation] --> D[rag_retrieval] --> E[model_router] --> F[llm_analysis] --> G[maintenance_decision]
  G -->|CREATE_DRAFT and no open WO| H[draft_generation] --> I[draft_validation]
  I -->|valid| J[mcp_draft_creation] --> Z[finalize]
  I -->|invalid| Z
  G -->|MONITOR / INSPECT_FIRST / INSUFFICIENT_EVIDENCE| Z
  A -.error.-> Z
  B -.error.-> Z
"""

"""Conditional edges of the LangGraph workflow (shared by LangGraph and the sequential fallback runner)."""
def _guard(nxt: str):
    return lambda s: "finalize" if s.get("error") else nxt

def after_decision(s: dict) -> str:
    if s.get("error"): return "finalize"
    rec = s.get("recommendation") or {}
    return "draft_generation" if rec.get("decision") == "CREATE_DRAFT" and not s.get("duplicate_work_order") else "finalize"

def after_validation(s: dict) -> str:
    return "finalize" if (s.get("error") or s.get("draft_errors")) else "mcp_draft_creation"

TRANSITIONS = {  # node -> (router fn, possible targets)
    "initialize": (_guard("mcp_context"), ["mcp_context", "finalize"]),
    "mcp_context": (_guard("evidence_preparation"), ["evidence_preparation", "finalize"]),
    "evidence_preparation": (_guard("rag_retrieval"), ["rag_retrieval", "finalize"]),
    "rag_retrieval": (_guard("model_router"), ["model_router", "finalize"]),
    "model_router": (_guard("llm_analysis"), ["llm_analysis", "finalize"]),
    "llm_analysis": (_guard("maintenance_decision"), ["maintenance_decision", "finalize"]),
    "maintenance_decision": (after_decision, ["draft_generation", "finalize"]),
    "draft_generation": (_guard("draft_validation"), ["draft_validation", "finalize"]),
    "draft_validation": (after_validation, ["mcp_draft_creation", "finalize"]),
    "mcp_draft_creation": (lambda s: "finalize", ["finalize"]),
}

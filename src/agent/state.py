"""Typed LangGraph state (JSON-serialisable values only, so checkpointing works)."""
from typing import Any, TypedDict

class AgentState(TypedDict, total=False):
    asset_id: str; risk_event_id: str; user_question: str; correlation_id: str
    asset: dict; risk_event: dict; sensor_history: dict; maintenance_history: list; work_orders: list
    evidence_context: dict; retrieved: list; retrieval_debug: dict; routing: dict
    explanation: dict; recommendation: dict; available_parts: list
    draft: dict; draft_errors: list; draft_result: dict; duplicate_work_order: str
    llm_calls: list; warnings: list; trace: list; error: str; result: dict

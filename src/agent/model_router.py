"""Model Router: picks OPEN vs FRONTIER AFTER evidence retrieval and BEFORE LLM analysis. Never changes risk or detects anomalies."""
from __future__ import annotations
from typing import Optional
from src.common.config import Settings
from src.common.contracts import ModelRoutingDecision
from src.common.enums import ModelType, RiskLevel

class ModelRouter:
    def __init__(self, s: Settings): self.s = s; self.cfg = s.routing
    def decide(self, risk_level: str, ctx: dict) -> ModelRoutingDecision:
        """ctx: n_anomalous_sensors, directions(list), n_failure_modes, signal_confidence, user_question, criticality, confirmed_fault."""
        base = self.cfg["routing"][risk_level]; esc = self.cfg["escalation"]; signals: list[str] = []
        if risk_level != "LOW":
            if ctx.get("n_anomalous_sensors", 0) >= 2: signals.append(f"{ctx['n_anomalous_sensors']} abnormal sensors")
            if ctx.get("criticality") in ("HIGH", "CRITICAL"): signals.append(f"{ctx['criticality']} criticality asset")
            if ctx.get("confirmed_fault"): signals.append("confirmed fault")
            reason = f"{risk_level} risk -> frontier model" + (f" ({'; '.join(signals)})" if signals else "")
            return self._mk(base, risk_level, reason, False, signals)
        if ctx.get("n_anomalous_sensors", 0) >= esc["min_anomalous_sensors"]: signals.append("multiple abnormal sensors")
        if ctx.get("n_failure_modes", 0) >= esc["min_plausible_failure_modes"]: signals.append("several plausible failure modes")
        if 0 < ctx.get("signal_confidence", 1.0) < esc["low_signal_confidence_below"] and ctx.get("n_anomalous_sensors", 0) > 0: signals.append("low-confidence/ambiguous signal")
        if esc.get("conflicting_directions") and len(set(ctx.get("directions", []))) > 1: signals.append("sensors move in conflicting directions")
        q = (ctx.get("user_question") or "").lower()
        if any(k in q for k in esc["complex_question_keywords"]): signals.append("complex maintenance recommendation requested")
        if signals: return self._mk("frontier", risk_level, "LOW risk escalated to frontier: " + "; ".join(signals), True, signals)
        return self._mk(base, risk_level, "LOW risk, routine single-signal case -> open model", False, [])
    def _mk(self, mt: str, risk: str, reason: str, esc: bool, signals: list) -> ModelRoutingDecision:
        return ModelRoutingDecision(model_type=ModelType(mt), deployment=self.s.deployment_for(mt), risk_level=RiskLevel(risk), routing_reason=reason, escalated=esc, signals=signals)

def estimate_cost(pricing: dict, model_type: str, prompt_tokens: Optional[int], completion_tokens: Optional[int]) -> Optional[float]:
    """USD from configured per-1M-token prices. Returns None (unavailable) when usage was not reported."""
    if prompt_tokens is None or completion_tokens is None: return None
    p = pricing[model_type]; return round((prompt_tokens * p["input"] + completion_tokens * p["output"]) / 1e6, 6)

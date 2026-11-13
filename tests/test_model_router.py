from src.agent.model_router import ModelRouter, estimate_cost
from src.common.config import load_settings

def _r(): s = load_settings(); s.open_deployment, s.frontier_deployment = "o", "f"; return ModelRouter(s), s

def test_risk_based_routing():
    r, _ = _r()
    assert r.decide("LOW", {}).model_type.value == "open"
    assert r.decide("MEDIUM", {}).model_type.value == "frontier" and r.decide("HIGH", {}).model_type.value == "frontier"

def test_low_risk_complexity_escalation():
    r, _ = _r()
    for ctx in ({"n_anomalous_sensors": 2}, {"n_failure_modes": 3}, {"directions": ["up", "down"]}, {"user_question": "recommend a work order"}, {"n_anomalous_sensors": 1, "signal_confidence": 0.2}):
        d = r.decide("LOW", ctx); assert d.model_type.value == "frontier" and d.escalated and d.signals
    assert r.decide("LOW", {"n_anomalous_sensors": 1, "signal_confidence": 0.9}).model_type.value == "open"

def test_router_never_changes_risk_and_deployment_from_config():
    r, s = _r(); d = r.decide("HIGH", {}); assert d.risk_level.value == "HIGH" and d.deployment == "f"

def test_cost_estimation_and_unavailable_usage():
    p = load_settings().routing["pricing_usd_per_1m_tokens"]
    assert estimate_cost(p, "open", 1_000_000, 1_000_000) == 0.75 and estimate_cost(p, "open", None, None) is None

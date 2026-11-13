from src.common.config import load_settings
from src.common.contracts import DetectionEvidence
from src.common.enums import AnomalyType
from src.detection.risk_engine import compute_risk

def ev(sensor="vibration", sev=0.8, breach="WARNING", hours=100, slope=7.0, atype=AnomalyType.PERSISTENT_ABNORMALITY):
    return DetectionEvidence(asset_id="A", sensor_name=sensor, unit="u", detected_at="t", window_start="a", window_end="b", baseline_mean=1, baseline_std=.1, current_mean=2,
        z_score=8, trend_slope_per_day=.1, trend_slope_pct_per_day=slope, deviation_pct=80, direction="up", threshold_breach=breach, anomaly_type=atype, sustained_hours=hours, severity=sev)

def test_no_anomaly_is_low():
    r = compute_risk({"asset_id": "A", "criticality": "HIGH"}, [], 30, None, load_settings().risk)
    assert r.risk_level.value == "LOW" and r.risk_score < 10

def test_more_sensors_and_criticality_raise_score():
    rc = load_settings().risk; a1 = {"asset_id": "A", "criticality": "LOW"}; a2 = {"asset_id": "A", "criticality": "CRITICAL"}
    one = compute_risk(a1, [ev()], 100, None, rc); two = compute_risk(a1, [ev(), ev("temperature")], 100, None, rc); crit = compute_risk(a2, [ev()], 100, None, rc)
    assert two.risk_score > one.risk_score and crit.risk_score > one.risk_score

def test_confirmed_fault_floor_and_type():
    rc = load_settings().risk; r = compute_risk({"asset_id": "A", "criticality": "LOW"}, [], 10, {"maintenance_date": "2026-11-01", "description": "crack"}, rc)
    assert r.confirmed_fault and r.anomaly_type == AnomalyType.CONFIRMED_FAULT and r.risk_level.value == "HIGH" and r.risk_score >= rc["confirmed_fault_floor"]

def test_isolated_capped():
    rc = load_settings().risk; r = compute_risk({"asset_id": "A", "criticality": "CRITICAL"}, [ev(atype=AnomalyType.ISOLATED_ANOMALY, sev=1.0)], 400, None, rc)
    assert r.risk_score <= rc["isolated_anomaly_cap"] and r.risk_level.value == "LOW"

def test_score_in_range_and_explained():
    r = compute_risk({"asset_id": "A", "criticality": "CRITICAL"}, [ev(sev=1, breach="CRITICAL"), ev("temperature", 1, "CRITICAL"), ev("current", 1, "CRITICAL")], 400, None, load_settings().risk)
    assert 0 <= r.risk_score <= 100 and r.breakdown and r.risk_reason

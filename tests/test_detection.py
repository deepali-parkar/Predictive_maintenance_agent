import pandas as pd
from src.common.config import load_settings
from src.detection.anomaly_detector import analyze_sensors, breach_level
from src.detection.detection_service import assess_asset

def _series(n=720, shift_from=None, shift=0.0, seed=1):
    import numpy as np
    r = np.random.default_rng(seed); idx = pd.date_range("2026-10-10", periods=n, freq="h"); v = 2.5 * (1 + r.normal(0, 0.05, n))
    if shift_from is not None: v[shift_from:] *= 1 + shift
    return pd.DataFrame({"timestamp": idx, "sensor_name": "vibration", "value": v, "unit": "mm/s"})

def test_healthy_series_not_flagged():
    s = load_settings(); a = {"asset_id": "X", "asset_type": "pump", "criticality": "MEDIUM"}
    r = assess_asset(a, _series(), None, None, s.detection, s.risk)
    assert r.risk_level.value == "LOW" and r.anomaly_type.value == "NONE" and not r.evidence

def test_sustained_shift_flagged_with_evidence():
    s = load_settings(); a = {"asset_id": "X", "asset_type": "pump", "criticality": "MEDIUM"}
    r = assess_asset(a, _series(shift_from=600, shift=1.0), None, None, s.detection, s.risk)
    assert r.evidence and r.evidence[0].sensor_name == "vibration" and r.evidence[0].z_score > 3 and r.risk_score > 20

def test_single_spike_is_isolated_and_low():
    s = load_settings(); a = {"asset_id": "X", "asset_type": "pump", "criticality": "LOW"}
    df = _series(); df.loc[df.index[-3], "value"] = 2.5 * 2.2
    r = assess_asset(a, df, None, None, s.detection, s.risk)
    assert r.anomaly_type.value in ("ISOLATED_ANOMALY", "NONE") and r.risk_level.value == "LOW"

def test_missing_values_not_zero_filled():
    s = load_settings(); df = _series(); df.loc[df.index[100:110], "value"] = float("nan"); df = df.dropna()
    d = analyze_sensors("pump", df, s.detection)["vibration"]
    assert d.features["value"].iloc[100:110].isna().all()

def test_breach_level():
    th = {"warn_high": 4.0, "crit_high": 6.0}
    assert breach_level(3, th) == "NONE" and breach_level(4.5, th) == "WARNING" and breach_level(6.5, th) == "CRITICAL"

def test_unknown_sensor_without_thresholds_still_analysed():
    s = load_settings(); df = _series(shift_from=600, shift=1.0); df["sensor_name"] = "rpm"
    assert "rpm" in analyze_sensors("pump", df, s.detection)

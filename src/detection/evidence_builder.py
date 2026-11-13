"""Builds DetectionEvidence objects from SensorDetection results and the persisted evidence JSON."""
from __future__ import annotations
import numpy as np, pandas as pd
from src.common.contracts import DetectionEvidence, RiskAssessment
from src.common.enums import AnomalyType
from src.detection.anomaly_detector import SensorDetection, breach_level

def build_evidence(asset_id: str, d: SensorDetection, as_of: pd.Timestamp, cfg: dict, slope_ref: float):
    """Return a DetectionEvidence for an ACTIVE sustained window (ending within recent_window_hours of as_of) or an isolated spike; else None."""
    f = d.features; recent = as_of - pd.Timedelta(hours=cfg["recent_window_hours"]); last = f.dropna(subset=["roll_mean"])
    if last.empty: return None
    row = last.iloc[-1]; fmt = lambda t: pd.Timestamp(t).strftime("%Y-%m-%d %H:%M:%S")
    active = [w for w in d.windows if w[1] >= recent]
    spikes = [t for t in d.spikes if t >= recent]
    if not active and not spikes: return None
    cur = float(row["roll_mean"]); slope = float(row["slope_per_day"]) if not np.isnan(row["slope_per_day"]) else 0.0
    spct = slope / abs(d.baseline_mean) * 100; direction = "up" if cur >= d.baseline_mean else "down"; th = d.thresholds
    br = breach_level(cur, th)
    tw = th.get("warn_high" if direction == "up" else "warn_low"); tc = th.get("crit_high" if direction == "up" else "crit_low")
    if active:
        ws, we, hrs = active[-1]; aligned = spct if direction == "up" else -spct
        rising = aligned >= 0.5 * slope_ref; atype = AnomalyType.PREDICTED_DEGRADATION if rising and br != "CRITICAL" else AnomalyType.PERSISTENT_ABNORMALITY
        rules = [f"ZSCORE>={cfg['z_threshold']}&DEV>={cfg['min_deviation_pct']}%", f"SUSTAINED_{hrs:.0f}h"] + ([f"THRESHOLD_{br}"] if br != "NONE" else []) + (["TREND_ALIGNED"] if rising else [])
    else:
        ws = we = spikes[-1]; hrs = 0.0; atype = AnomalyType.ISOLATED_ANOMALY; rules = [f"SPIKE_Z>={cfg['spike_z_threshold']}"]
    dev = float(row["dev_pct"]); sat = th.get("sat_dev_pct", 60.0)
    sev = max(min(1.0, abs(dev) / sat), {"NONE": 0.0, "WARNING": 0.6, "CRITICAL": 1.0}[br]) if active else min(1.0, abs(float(row["raw_z"])) / 12)
    return DetectionEvidence(asset_id=asset_id, sensor_name=d.sensor, unit=d.unit, detected_at=fmt(as_of), window_start=fmt(ws), window_end=fmt(we),
        baseline_mean=round(d.baseline_mean, 4), baseline_std=round(d.baseline_std, 4), current_mean=round(cur, 4), z_score=round(float(row["z"]), 2),
        trend_slope_per_day=round(slope, 4), trend_slope_pct_per_day=round(spct, 3), deviation_pct=round(dev, 2), direction=direction,
        threshold_warning=tw, threshold_critical=tc, threshold_breach=br, detection_rule="+".join(rules), anomaly_type=atype,
        sustained_hours=round(hrs, 1), severity=round(float(sev), 3))

def evidence_json(r: RiskAssessment, confirmed_record: dict | None = None) -> dict:
    return {"summary": r.risk_reason, "predicted_risk": r.predicted_risk, "trend_summary": r.trend_summary, "signal_confidence": r.signal_confidence,
            "monitoring_urgency": r.monitoring_urgency, "risk_breakdown": r.breakdown, "sensors": [e.model_dump(mode="json") for e in r.evidence],
            "confirmed_fault_record": confirmed_record}

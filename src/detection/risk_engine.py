"""Transparent, configurable risk scoring. Deterministic; never calls an LLM."""
from __future__ import annotations
from src.common.contracts import DetectionEvidence, RiskAssessment
from src.common.enums import AnomalyType, RiskLevel

def _level(score: float, rc: dict) -> RiskLevel:
    t = rc["level_thresholds"]
    return RiskLevel.HIGH if score >= t["high"] else RiskLevel.MEDIUM if score >= t["medium"] else RiskLevel.LOW

def _trend_norm(e: DetectionEvidence, ref: float) -> float:
    aligned = e.trend_slope_pct_per_day if e.direction == "up" else -e.trend_slope_pct_per_day
    return max(0.0, min(1.0, aligned / ref)) if ref else 0.0

def compute_risk(asset: dict, evidence: list[DetectionEvidence], days_since_service: float | None, confirmed_fault: dict | None,
                 rc: dict, slope_refs: dict | None = None) -> RiskAssessment:
    w = rc["weights"]; slope_refs = slope_refs or {}
    service = min(1.0, (days_since_service or 0) / rc["service_saturation_days"]) if days_since_service is not None else 0.0
    sustained = [e for e in evidence if e.anomaly_type in (AnomalyType.PERSISTENT_ABNORMALITY, AnomalyType.PREDICTED_DEGRADATION)]
    isolated = [e for e in evidence if e.anomaly_type == AnomalyType.ISOLATED_ANOMALY]
    crit = rc["criticality_factor"].get(str(asset.get("criticality", "MEDIUM")), 1.0)
    comps: dict = {"service_age": round(service, 3), "criticality_factor": crit}
    if sustained:
        sev = max(e.severity for e in sustained)
        trend = max(_trend_norm(e, slope_refs.get(e.sensor_name, 5.0)) for e in sustained)
        breach = max(rc["breach_values"][e.threshold_breach] for e in sustained)
        multi = rc["multi_sensor_values"][min(len(sustained), 3)]
        pers = min(1.0, max(e.sustained_hours for e in sustained) / rc["persistence_saturation_hours"])
        comps.update(severity=round(sev, 3), trend=round(trend, 3), threshold_breach=round(breach, 3), multi_sensor=multi, persistence=round(pers, 3))
        score = 100 * (w["severity"] * sev + w["trend"] * trend + w["threshold_breach"] * breach + w["multi_sensor"] * multi
                       + w["persistence"] * pers + w["service_age"] * service) * crit
        atype = (AnomalyType.PREDICTED_DEGRADATION if all(e.anomaly_type == AnomalyType.PREDICTED_DEGRADATION for e in sustained)
                 and all(e.threshold_breach != "CRITICAL" for e in sustained) else AnomalyType.PERSISTENT_ABNORMALITY)
    elif isolated:
        sev = max(e.severity for e in isolated); comps["severity"] = round(sev, 3)
        score = min(rc["isolated_anomaly_cap"], 100 * (w["severity"] * sev + w["service_age"] * service)); atype = AnomalyType.ISOLATED_ANOMALY
    else:
        score = 100 * w["service_age"] * rc["no_anomaly_service_weight"] * service; atype = AnomalyType.NONE
    score = min(100.0, score); reason_bits = []
    if confirmed_fault:
        score = max(score, rc["confirmed_fault_floor"]); atype = AnomalyType.CONFIRMED_FAULT
        reason_bits.append(f"CONFIRMED FAULT recorded on {confirmed_fault['maintenance_date']}: {confirmed_fault.get('description', '')}")
    level = _level(score, rc)
    active = sustained or isolated
    for e in sustained:
        reason_bits.append(f"{e.sensor_name} {e.direction} {abs(e.deviation_pct):.0f}% vs baseline for {e.sustained_hours:.0f}h (breach: {e.threshold_breach}, z={e.z_score:.1f})")
    for e in isolated: reason_bits.append(f"isolated {e.sensor_name} excursion (not sustained)")
    if len(sustained) > 1: reason_bits.append(f"{len(sustained)} sensors abnormal simultaneously")
    if not reason_bits: reason_bits.append("no abnormal behaviour detected")
    z = max([abs(e.z_score) for e in sustained] or [0]); n = len(sustained)
    conf = 0.0 if not sustained else round(0.35 * min(1, max(e.sustained_hours for e in sustained) / 48) + 0.25 * min(1, z / 6)
                                         + 0.2 * (1 if any(e.threshold_breach != "NONE" for e in sustained) else 0) + 0.2 * min(1, n / 2), 3)
    pred = {AnomalyType.CONFIRMED_FAULT: "Confirmed fault (recorded by maintenance inspection)", AnomalyType.PREDICTED_DEGRADATION: "Predicted degradation: sustained trending deviation, no confirmed fault",
            AnomalyType.PERSISTENT_ABNORMALITY: "Persistent abnormality: sustained deviation / threshold breach, cause not confirmed",
            AnomalyType.ISOLATED_ANOMALY: "Isolated anomaly: short excursion, not sustained", AnomalyType.NONE: "No anomaly"}[atype]
    trend = "; ".join(f"{e.sensor_name}: {e.current_mean:.2f}{e.unit} vs baseline {e.baseline_mean:.2f} ({e.trend_slope_pct_per_day:+.1f}%/day)" for e in active) or "stable"
    starts = [e.window_start for e in active]; ends = [e.window_end for e in active]
    return RiskAssessment(asset_id=asset["asset_id"], risk_level=level, risk_score=round(score, 1), risk_reason="; ".join(reason_bits), anomaly_type=atype,
                          evidence=list(active), affected_sensors=sorted({e.sensor_name for e in active}), trend_summary=trend, signal_confidence=conf,
                          confirmed_fault=bool(confirmed_fault), predicted_risk=pred, monitoring_urgency=rc["monitoring_urgency"][level.value], breakdown=comps,
                          window_start=min(starts) if starts else None, window_end=max(ends) if ends else None)

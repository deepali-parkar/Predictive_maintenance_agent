"""Orchestrates detection + risk for assets stored in SQLite and persists RiskEvents."""
from __future__ import annotations
from datetime import datetime
from typing import Optional
import pandas as pd
from src.common.config import get_settings
from src.common.contracts import RiskAssessment
from src.common.logging_config import get_logger
from src.detection.anomaly_detector import analyze_sensors
from src.detection.evidence_builder import build_evidence, evidence_json
from src.detection.risk_engine import compute_risk
from src.maintenance_app.database import transaction
from src.maintenance_app.services import get_services

log = get_logger("detection")

def assess_asset(asset: dict, readings: pd.DataFrame, last_service: Optional[str], confirmed: Optional[dict], det_cfg: dict, risk_cfg: dict,
                 as_of: Optional[pd.Timestamp] = None) -> RiskAssessment:
    """Pure function: readings in, RiskAssessment out (used by the service, dashboard and evaluation)."""
    cfg = det_cfg["analysis"]; as_of = as_of or readings["timestamp"].max()
    dets = analyze_sensors(asset["asset_type"], readings, det_cfg, as_of)
    ev, refs = [], {}
    for s, d in dets.items():
        ref = d.thresholds.get("slope_ref_pct_per_day", det_cfg["sensor_defaults"]["slope_ref_pct_per_day"]); refs[s] = ref
        e = build_evidence(asset["asset_id"], d, as_of, cfg, ref)
        if e is not None: ev.append(e)
    days = (as_of - pd.Timestamp(last_service)).days if last_service else None
    r = compute_risk(asset, ev, days, confirmed, risk_cfg, refs)
    if not dets and not confirmed:    # nothing analysable: say so instead of implying the asset is healthy
        need = cfg["min_baseline_points"]
        r = r.model_copy(update={"risk_reason": f"Not assessed: insufficient history (need >= {need} readings within the first {cfg['baseline_hours']} h of data to form a baseline)",
                                 "predicted_risk": "Not assessed"})
    return r

def run_detection(conn, asset_ids: Optional[list[str]] = None, as_of: Optional[str] = None, settings=None) -> list[dict]:
    s = settings or get_settings(); svc = get_services(conn); out = []
    for asset in svc.assets.list():
        if asset_ids and asset["asset_id"] not in asset_ids: continue
        df = svc.sensors.history(asset["asset_id"])
        if df.empty: log.warning("no readings", extra={"ctx": {"asset_id": asset["asset_id"]}}); continue
        ts = pd.Timestamp(as_of) if as_of else None
        confirmed = svc.maintenance.confirmed_fault(asset["asset_id"])
        r = assess_asset(asset, df, svc.maintenance.last_service_date(asset["asset_id"]), confirmed, s.detection, s.risk, ts)
        detected_at = (ts or df["timestamp"].max()).strftime("%Y-%m-%d %H:%M:%S")
        status = "NORMAL" if r.anomaly_type.value == "NONE" else "ACTIVE"
        cur = svc.risks.current(asset["asset_id"]); version = f"{s.detection['version']}/{s.risk['version']}"
        if cur and cur["detection_version"] == version and cur["window_start"] == r.window_start and cur["risk_level"] == r.risk_level.value \
           and abs(cur["risk_score"] - r.risk_score) < 0.05 and cur["anomaly_type"] == r.anomaly_type.value and cur["status"] == status:
            out.append(cur); continue
        with transaction(conn):
            rid = svc.risks.insert({"asset_id": asset["asset_id"], "detected_at": detected_at, "window_start": r.window_start, "window_end": r.window_end,
                "risk_level": r.risk_level.value, "risk_score": r.risk_score, "anomaly_type": r.anomaly_type.value, "affected_sensors": r.affected_sensors,
                "evidence": evidence_json(r, confirmed), "confirmed_fault": r.confirmed_fault, "status": status, "detection_version": version})
            svc.risks.supersede(asset["asset_id"], rid)
            svc.audit.record("SYSTEM:detection", "CREATE_RISK_EVENT", "risk_event", rid, None, {"risk_level": r.risk_level.value, "score": r.risk_score})
        out.append(svc.risks.get(rid))
    return out

"""Streamlit-independent data access for the dashboard (queries SQLite through repositories/services)."""
from __future__ import annotations
from typing import Optional
import pandas as pd
from src.detection.anomaly_detector import SensorDetection, analyze_sensors
from src.maintenance_app.services import get_services

HEALTH = {"LOW": "🟢 Healthy", "MEDIUM": "🟡 Watch", "HIGH": "🔴 At risk", "UNASSESSED": "⚪ Not assessed"}

def build_overview_df(conn) -> pd.DataFrame:
    svc = get_services(conn); rows = []
    for a in svc.assets.list():
        r = svc.risks.current(a["asset_id"]); latest = svc.sensors.latest(a["asset_id"]); lvl = r["risk_level"] if r else "UNASSESSED"
        if r and (r["evidence"] or {}).get("predicted_risk") == "Not assessed": lvl = "UNASSESSED"
        rows.append({"asset_id": a["asset_id"], "asset_name": a["asset_name"], "asset_type": a["asset_type"], "criticality": a["criticality"], "operating_status": a["operating_status"],
                     "risk_level": lvl, "risk_score": r["risk_score"] if r else 0.0, "health": HEALTH[lvl], "anomaly_type": r["anomaly_type"] if r and lvl != "UNASSESSED" else "-",
                     "affected_sensors": ", ".join(r["affected_sensors"]) if r else "",
                     "latest_readings": " | ".join(f"{k}: {v['value']:.2f}{v['unit']}" for k, v in sorted(latest.items())),
                     "active_risk_events": len(svc.risks.list(a["asset_id"], "ACTIVE")), "last_maintenance": svc.maintenance.last_date(a["asset_id"])})
    return pd.DataFrame(rows)

def asset_detections(conn, asset_id: str, det_cfg: dict) -> dict[str, SensorDetection]:
    svc = get_services(conn); a = svc.assets.get(asset_id); df = svc.sensors.history(asset_id)
    return analyze_sensors(a["asset_type"], df, det_cfg) if (a and not df.empty) else {}

def date_bounds(conn, asset_id: str) -> tuple[Optional[pd.Timestamp], Optional[pd.Timestamp]]:
    lo, hi = get_services(conn).sensors.time_range(asset_id)
    return (pd.Timestamp(lo), pd.Timestamp(hi)) if lo else (None, None)

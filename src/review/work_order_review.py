"""Read models for the Work Order Review page."""
from src.maintenance_app.services import get_services

def review_bundle(conn, work_order_id: str) -> dict:
    svc = get_services(conn); wo = svc.work_orders.get(work_order_id)
    return {"work_order": wo, "asset": svc.assets.get(wo["asset_id"]), "risk_event": svc.risks.get(wo["risk_event_id"]) if wo["risk_event_id"] else None,
            "spares": svc.spares.compatible((svc.assets.get(wo["asset_id"]) or {}).get("asset_type", "")), "audit": svc.audit.trail(work_order_id)}

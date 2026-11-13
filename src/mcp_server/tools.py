"""MCP tool implementations (transport-independent). Exposed by server.py (FastMCP) and by the in-process client.
No arbitrary SQL is exposed: every tool is a fixed, validated operation on the service layer of the SAME operational SQLite DB."""
from __future__ import annotations
from typing import Any, Callable, Optional
import pandas as pd
from src.common.contracts import PartRequest, WorkOrderRequest
from src.common.enums import Priority
from src.common.exceptions import MCPError, NotFoundError, PermissionDenied, ValidationFailed
from src.common.logging_config import get_correlation_id, get_logger, set_correlation_id
from src.maintenance_app.database import connect, init_db
from src.maintenance_app.services import get_services
from src.mcp_server.permissions import check

log = get_logger("mcp")

def _need(args: dict, *names):
    for n in names:
        if args.get(n) in (None, ""): raise ValidationFailed(f"missing required argument '{n}'")

def _asset_or_404(svc, asset_id: str) -> dict:
    a = svc.assets.get(asset_id)
    if not a: raise NotFoundError(f"asset '{asset_id}' not found")
    return a

def get_asset(svc, a: dict) -> dict:
    _need(a, "asset_id"); asset = _asset_or_404(svc, a["asset_id"])
    return {**asset, "current_risk": svc.risks.current(asset["asset_id"]), "last_maintenance_date": svc.maintenance.last_date(asset["asset_id"]),
            "last_service_date": svc.maintenance.last_service_date(asset["asset_id"]), "latest_readings": svc.sensors.latest(asset["asset_id"])}

def get_sensor_history(svc, a: dict) -> dict:
    _need(a, "asset_id"); _asset_or_404(svc, a["asset_id"]); mp = int(a.get("max_points", 300))
    if not 10 <= mp <= 5000: raise ValidationFailed("max_points must be 10..5000")
    df = svc.sensors.history(a["asset_id"], None, a.get("start"), a.get("end"))
    if a.get("sensors"): df = df[df["sensor_name"].isin(a["sensors"])]
    out = {}
    for s, g in df.groupby("sensor_name"):
        stride = max(1, -(-len(g) // mp)); pts = g.iloc[::stride]
        if g.index[-1] != pts.index[-1]: pts = pd.concat([pts, g.iloc[[-1]]])
        out[s] = {"unit": g["unit"].iloc[0], "n_points_total": int(len(g)), "stride": stride,
                  "summary": {"first": round(float(g["value"].iloc[0]), 3), "last": round(float(g["value"].iloc[-1]), 3), "mean": round(float(g["value"].mean()), 3),
                              "min": round(float(g["value"].min()), 3), "max": round(float(g["value"].max()), 3)},
                  "points": [[t.strftime("%Y-%m-%d %H:%M:%S"), round(float(v), 3)] for t, v in zip(pts["timestamp"], pts["value"])]}
    return {"asset_id": a["asset_id"], "start": a.get("start"), "end": a.get("end"), "sensors": out}

def get_risk_events(svc, a: dict) -> dict:
    _need(a, "asset_id"); _asset_or_404(svc, a["asset_id"])
    if a.get("risk_event_id"):
        e = svc.risks.get(a["risk_event_id"])
        if not e or e["asset_id"] != a["asset_id"]: raise NotFoundError(f"risk event {a['risk_event_id']} not found for asset")
        return {"asset_id": a["asset_id"], "risk_events": [e]}
    return {"asset_id": a["asset_id"], "risk_events": svc.risks.list(a["asset_id"], a.get("status"), int(a.get("limit", 5)))}

def get_maintenance_history(svc, a: dict) -> dict:
    _need(a, "asset_id"); _asset_or_404(svc, a["asset_id"])
    return {"asset_id": a["asset_id"], "records": svc.maintenance.list(a["asset_id"], int(a.get("limit", 20)))}

def get_asset_work_orders(svc, a: dict) -> dict:
    _need(a, "asset_id"); _asset_or_404(svc, a["asset_id"])
    return {"asset_id": a["asset_id"], "work_orders": [{k: w[k] for k in ("work_order_id", "title", "priority", "status", "created_at", "risk_event_id")}
                                                      for w in svc.work_orders.list(a["asset_id"], a.get("status"))]}

def check_spares(svc, a: dict) -> dict:
    atype = a.get("asset_type")
    if a.get("asset_id"): atype = _asset_or_404(svc, a["asset_id"])["asset_type"]
    if not atype and not a.get("part_ids"): raise ValidationFailed("provide asset_id, asset_type or part_ids")
    parts = [svc.spares.get(p) for p in a["part_ids"]] if a.get("part_ids") else svc.spares.compatible(atype)
    res = []
    for p in parts:
        if p is None: continue
        res.append({**p, "in_stock": p["quantity_available"] > 0, "below_reorder": p["quantity_available"] <= p["reorder_level"],
                    "compatible": (atype is None) or any(atype.lower() == t.strip().lower() or t.strip().lower() == "all" for t in (p["compatible_asset_types"] or "").replace(";", ",").split(","))})
    missing = [p for p in (a.get("part_ids") or []) if svc.spares.get(p) is None]
    return {"asset_type": atype, "parts": res, "unknown_part_ids": missing}

def create_draft_work_order(svc, a: dict) -> dict:
    """Creates a DRAFT only. Never approves/completes/executes."""
    try:
        payload = dict(a); payload["required_parts"] = [PartRequest(**p) if isinstance(p, dict) else p for p in payload.get("required_parts") or []]
        req = WorkOrderRequest(**payload)
    except Exception as e:
        return {"work_order_id": None, "status": "INVALID", "created_at": "", "validation_result": {"valid": False, "errors": [f"schema: {e}"]}}
    try:
        r = svc.work_orders.create_draft(req)
        return {**r, "validation_result": {"valid": True, "errors": []}}
    except ValidationFailed as e:
        return {"work_order_id": None, "status": "INVALID", "created_at": "", "validation_result": {"valid": False, "errors": e.errors or [str(e)]}}

TOOLS: dict[str, Callable] = {"get_asset": get_asset, "get_sensor_history": get_sensor_history, "get_risk_events": get_risk_events,
    "get_maintenance_history": get_maintenance_history, "get_asset_work_orders": get_asset_work_orders, "check_spares": check_spares,
    "create_draft_work_order": create_draft_work_order}

class ToolRegistry:
    """Dispatches tool calls with permission checks, structured logging and audit records."""
    def __init__(self, db_path=None, role: str = "agent"):
        self.db_path, self.role = db_path, role
    def call(self, name: str, args: Optional[dict] = None, role: Optional[str] = None, correlation_id: Optional[str] = None) -> dict:
        role = role or self.role; args = dict(args or {})
        if correlation_id: set_correlation_id(correlation_id)
        if name not in TOOLS: raise MCPError(f"unknown tool '{name}'")
        check(role, name)
        conn = connect(self.db_path); init_db(conn); svc = get_services(conn)
        try:
            result = TOOLS[name](svc, args)
            svc.audit.record(f"MCP:{role}", "TOOL_CALL", "mcp_tool", name, None, {"args": {k: (v if len(str(v)) < 300 else "...") for k, v in args.items()}}, "", get_correlation_id())
            log.info("tool_call", extra={"ctx": {"tool": name, "role": role}})
            return result
        except (ValidationFailed, NotFoundError) as e:
            log.warning("tool_error", extra={"ctx": {"tool": name, "error": str(e)}}); raise
        finally:
            conn.close()

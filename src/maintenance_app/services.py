"""Service layer: business rules, validation, transactions, audit. Used by dashboard, MCP tools, agent (via MCP) and scripts."""
from __future__ import annotations
import json, sqlite3
from types import SimpleNamespace
from typing import Optional
from src.common.contracts import WorkOrderRequest
from src.common.enums import Priority, WorkOrderStatus
from src.common.exceptions import NotFoundError, PermissionDenied, ValidationFailed
from src.common.logging_config import get_correlation_id, get_logger
from src.maintenance_app import repositories as R
from src.maintenance_app.database import now_iso, transaction

log = get_logger("services")
PLANNER_ROLE, AGENT_ROLE = "planner", "agent"

class AuditService:
    def __init__(self, c): self.repo = R.AuditRepo(c)
    def record(self, actor, action, entity_type, entity_id, before=None, after=None, reason="", correlation_id=None):
        self.repo.add(actor, action, entity_type, entity_id, before, after, reason, correlation_id or get_correlation_id())
    def trail(self, entity_id=None, entity_type=None, limit=200): return self.repo.list(entity_id, entity_type, limit)

class ModelLogService:
    def __init__(self, c): self.repo = R.ModelLogRepo(c)
    def record(self, entry: dict): self.repo.add(entry)
    def all(self, limit=1000): return self.repo.list(limit)

class WorkOrderService:
    """Agent may only create DRAFTs. Only a planner may edit / approve / reject. Nothing here executes maintenance."""
    def __init__(self, c: sqlite3.Connection):
        self.c = c; self.repo = R.WorkOrderRepo(c); self.audit = AuditService(c)
        self.assets = R.AssetRepo(c); self.risks = R.RiskRepo(c); self.spares = R.SpareRepo(c)

    def validate_request(self, req: WorkOrderRequest) -> list[str]:
        errs = []
        if not self.assets.exists(req.asset_id): errs.append(f"unknown asset_id {req.asset_id}")
        if req.risk_event_id:
            ev = self.risks.get(req.risk_event_id)
            if not ev: errs.append(f"unknown risk_event_id {req.risk_event_id}")
            elif ev["asset_id"] != req.asset_id: errs.append("risk_event does not belong to asset")
        if not req.title.strip() or not req.problem_description.strip(): errs.append("title and problem_description are required")
        if not req.recommended_steps: errs.append("at least one recommended step required")
        if not req.evidence_references: errs.append("at least one evidence reference required")
        for p in req.required_parts:
            if not self.spares.get(p.part_id): errs.append(f"unknown part_id {p.part_id}")
        return errs

    def create_draft(self, req: WorkOrderRequest) -> dict:
        errs = self.validate_request(req)
        if errs: raise ValidationFailed("work order draft failed validation", errs)
        with transaction(self.c):
            wid = self.repo.next_id(); ts = now_iso()
            ev = {"evidence_references": req.evidence_references, "rationale": req.rationale}
            self.repo.insert({"work_order_id": wid, "asset_id": req.asset_id, "risk_event_id": req.risk_event_id, "title": req.title,
                              "problem_description": req.problem_description, "priority": req.priority.value if isinstance(req.priority, Priority) else str(req.priority),
                              "recommended_steps": req.recommended_steps, "status": WorkOrderStatus.DRAFT.value,
                              "created_by": req.requested_by, "created_at": ts, "evidence": ev})
            self.repo.set_parts(wid, [p.model_dump(mode="json") for p in req.required_parts])
            self.audit.record(req.requested_by, "CREATE_DRAFT", "work_order", wid, None, self.get(wid), req.rationale, req.correlation_id or None)
        return {"work_order_id": wid, "status": "DRAFT", "created_at": ts}

    def get(self, wid: str) -> dict:
        w = self.repo.get(wid)
        if not w: raise NotFoundError(f"work order {wid} not found")
        w["parts"] = self.repo.parts(wid); return w

    def list(self, asset_id=None, status=None): return self.repo.list(asset_id, status)

    @staticmethod
    def _require_planner(actor: str, role: str):
        if role != PLANNER_ROLE or actor.upper().startswith("AGENT"):
            raise PermissionDenied("only a human planner may edit, approve or reject work orders")

    def _require_draft(self, wid):
        w = self.get(wid)
        if w["status"] != "DRAFT": raise ValidationFailed(f"work order {wid} is {w['status']}; only DRAFT can be changed")
        return w

    def edit(self, wid: str, changes: dict, actor: str, role: str, reason: str = "") -> dict:
        self._require_planner(actor, role)
        allowed = {"title", "problem_description", "priority", "recommended_steps", "parts"}
        bad = set(changes) - allowed
        if bad: raise ValidationFailed(f"fields not editable: {sorted(bad)}")
        if "priority" in changes and changes["priority"] not in {p.value for p in Priority}: raise ValidationFailed("invalid priority")
        with transaction(self.c):
            before = self._require_draft(wid)
            parts = changes.pop("parts", None)
            if parts is not None:
                for p in parts:
                    if not self.spares.get(p["part_id"]): raise ValidationFailed(f"unknown part_id {p['part_id']}")
                self.repo.set_parts(wid, parts)
            if changes: self.repo.update(wid, dict(changes))
            after = self.get(wid); self.audit.record(actor, "EDIT_DRAFT", "work_order", wid, before, after, reason)
        return after

    def approve(self, wid: str, actor: str, role: str, reason: str = "") -> dict:
        self._require_planner(actor, role)
        with transaction(self.c):
            before = self._require_draft(wid)
            self.repo.update(wid, {"status": "APPROVED", "approved_by": actor, "approved_at": now_iso()})
            after = self.get(wid); self.audit.record(actor, "APPROVE", "work_order", wid, before, after, reason)
        return after

    def reject(self, wid: str, actor: str, role: str, reason: str) -> dict:
        self._require_planner(actor, role)
        if not reason or not reason.strip(): raise ValidationFailed("a rejection reason is required")
        with transaction(self.c):
            before = self._require_draft(wid)
            self.repo.update(wid, {"status": "REJECTED", "rejection_reason": reason})
            after = self.get(wid); self.audit.record(actor, "REJECT", "work_order", wid, before, after, reason)
        return after

class AssetAdminService:
    """Removes an asset and all its dependent rows (readings, risk events, drafts). Audited; refuses approved work orders unless force."""
    def __init__(self, c): self.c = c; self.assets = R.AssetRepo(c); self.audit = AuditService(c)
    def delete_asset(self, asset_id: str, actor: str, force: bool = False) -> dict:
        if not self.assets.exists(asset_id): raise NotFoundError(f"asset {asset_id} not found")
        counts = self.assets.counts(asset_id)
        if counts["approved_work_orders"] and not force: raise ValidationFailed(f"{asset_id} has approved work orders; deletion refused (force=True to override)")
        with transaction(self.c):
            before = self.assets.get(asset_id); self.assets.purge(asset_id)
            self.audit.record(actor, "DELETE_ASSET", "asset", asset_id, {**before, "removed_rows": counts}, None, "asset removed with dependent data")
        return counts

def get_services(conn: sqlite3.Connection) -> SimpleNamespace:
    """Aggregate of repositories + services bound to one connection of the single operational DB."""
    return SimpleNamespace(conn=conn, assets=R.AssetRepo(conn), sensors=R.SensorRepo(conn), risks=R.RiskRepo(conn),
                           maintenance=R.MaintenanceRepo(conn), spares=R.SpareRepo(conn), work_orders=WorkOrderService(conn),
                           audit=AuditService(conn), model_logs=ModelLogService(conn), asset_admin=AssetAdminService(conn))

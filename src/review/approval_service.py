"""Planner review actions. The ONLY code path that can approve / edit / reject drafts (planner role enforced in the service layer)."""
from __future__ import annotations
from typing import Optional
from src.maintenance_app.services import PLANNER_ROLE, WorkOrderService

class ApprovalService:
    def __init__(self, conn): self.wo = WorkOrderService(conn)
    def edit(self, wid: str, changes: dict, planner: str, reason: str = "") -> dict: return self.wo.edit(wid, dict(changes), planner, PLANNER_ROLE, reason)
    def approve(self, wid: str, planner: str, reason: str = "") -> dict: return self.wo.approve(wid, planner, PLANNER_ROLE, reason)
    def reject(self, wid: str, planner: str, reason: str) -> dict: return self.wo.reject(wid, planner, PLANNER_ROLE, reason)

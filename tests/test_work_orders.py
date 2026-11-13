from tests.helpers import make_env
from src.common.contracts import PartRequest, WorkOrderRequest
from src.common.exceptions import PermissionDenied, ValidationFailed
from src.maintenance_app.database import connect
from src.maintenance_app.services import get_services

def _draft(svc):
    rid = svc.risks.current("PMP-106")["risk_event_id"]
    return svc.work_orders.create_draft(WorkOrderRequest(asset_id="PMP-106", risk_event_id=rid, title="T", problem_description="P", priority="HIGH", recommended_steps=["s"],
        required_parts=[PartRequest(part_id="SP-BRG-6309", quantity=2)], evidence_references=["SENSOR:vibration"], rationale="r"))

def test_create_draft_persists_parts_and_audit():
    s, db = make_env(); svc = get_services(connect(db)); r = _draft(svc); wo = svc.work_orders.get(r["work_order_id"])
    assert wo["status"] == "DRAFT" and wo["parts"][0]["quantity"] == 2 and svc.audit.trail(r["work_order_id"])[0]["action"] == "CREATE_DRAFT"

def test_validation_rejects_bad_requests():
    s, db = make_env(); svc = get_services(connect(db))
    for bad in (dict(asset_id="NOPE"), dict(risk_event_id="RE-NOPE"), dict(evidence_references=[]), dict(recommended_steps=[])):
        base = dict(asset_id="PMP-106", risk_event_id=None, title="T", problem_description="P", priority="HIGH", recommended_steps=["s"], evidence_references=["x"]); base.update(bad)
        try: svc.work_orders.create_draft(WorkOrderRequest(**base)); assert False, bad
        except ValidationFailed: pass

def test_agent_cannot_approve_edit_or_reject():
    s, db = make_env(); svc = get_services(connect(db)); wid = _draft(svc)["work_order_id"]
    for fn in (lambda: svc.work_orders.approve(wid, "AGENT:sentinel", "agent"), lambda: svc.work_orders.approve(wid, "AGENT:sentinel", "planner"),
               lambda: svc.work_orders.edit(wid, {"title": "x"}, "AGENT:sentinel", "agent"), lambda: svc.work_orders.reject(wid, "AGENT:sentinel", "agent", "no")):
        try: fn(); assert False
        except PermissionDenied: pass
    assert svc.work_orders.get(wid)["status"] == "DRAFT"

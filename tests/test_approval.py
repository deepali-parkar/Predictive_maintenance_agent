from tests.test_work_orders import _draft
from tests.helpers import make_env
from src.common.exceptions import ValidationFailed
from src.maintenance_app.database import connect
from src.maintenance_app.services import get_services
from src.review.approval_service import ApprovalService

def test_edit_then_approve_with_audit_before_after():
    s, db = make_env(); c = connect(db); svc = get_services(c); wid = _draft(svc)["work_order_id"]; ap = ApprovalService(c)
    e = ap.edit(wid, {"title": "New title", "priority": "URGENT", "parts": [{"part_id": "SP-GRS-EP2", "quantity": 1}]}, "planner.jane")
    assert e["title"] == "New title" and e["parts"][0]["part_id"] == "SP-GRS-EP2"
    a = ap.approve(wid, "planner.jane", "ok"); assert a["status"] == "APPROVED" and a["approved_by"] == "planner.jane" and a["approved_at"]
    acts = [x["action"] for x in svc.audit.trail(wid)]; assert acts[:2] == ["APPROVE", "EDIT_DRAFT"] and "CREATE_DRAFT" in acts
    ed = [x for x in svc.audit.trail(wid) if x["action"] == "EDIT_DRAFT"][0]; assert "Replace" not in ed["before_json"] and "New title" in ed["after_json"] and "T" in ed["before_json"]

def test_reject_requires_reason_and_final_states_immutable():
    s, db = make_env(); c = connect(db); svc = get_services(c); ap = ApprovalService(c); wid = _draft(svc)["work_order_id"]
    try: ap.reject(wid, "planner.jane", " "); assert False
    except ValidationFailed: pass
    r = ap.reject(wid, "planner.jane", "not needed"); assert r["status"] == "REJECTED" and r["rejection_reason"] == "not needed"
    for fn in (lambda: ap.approve(wid, "planner.jane"), lambda: ap.edit(wid, {"title": "x"}, "planner.jane")):
        try: fn(); assert False
        except ValidationFailed: pass

def test_failed_edit_rolls_back_atomically():
    s, db = make_env(); c = connect(db); svc = get_services(c); ap = ApprovalService(c); wid = _draft(svc)["work_order_id"]
    try: ap.edit(wid, {"title": "Changed", "parts": [{"part_id": "SP-FAKE"}]}, "planner.jane"); assert False
    except ValidationFailed: pass
    assert svc.work_orders.get(wid)["title"] == "T" and svc.work_orders.get(wid)["parts"][0]["part_id"] == "SP-BRG-6309"

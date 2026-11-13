from tests.helpers import make_env
from src.common.exceptions import MCPError, NotFoundError, PermissionDenied
from src.mcp_server.client import InProcessMCPClient
from src.mcp_server.tools import TOOLS, ToolRegistry

def test_all_spec_tools_exposed():
    assert set(TOOLS) == {"get_asset", "get_sensor_history", "get_risk_events", "get_maintenance_history", "get_asset_work_orders", "check_spares", "create_draft_work_order"}

def test_read_tools_return_real_data():
    s, db = make_env(); c = InProcessMCPClient(db)
    a = c.call("get_asset", asset_id="PMP-106"); assert a["criticality"] == "CRITICAL" and a["current_risk"]["risk_level"] == "HIGH"
    h = c.call("get_sensor_history", asset_id="PMP-106", sensors=["vibration"], max_points=50); assert len(h["sensors"]["vibration"]["points"]) <= 51
    assert c.call("get_maintenance_history", asset_id="PMP-106")["records"]
    assert c.call("get_risk_events", asset_id="PMP-106")["risk_events"][0]["evidence"]["sensors"]
    sp = c.call("check_spares", asset_id="PMP-106")["parts"]; assert any(p["part_id"] == "SP-SEAL-MS40" and p["compatible"] for p in sp)

def test_unknown_asset_and_missing_args():
    s, db = make_env(); c = InProcessMCPClient(db)
    for kw in ({"asset_id": "NOPE"}, {}):
        try: c.call("get_asset", **kw); assert False
        except Exception as e: assert isinstance(e, (NotFoundError, Exception))

def test_permissions_readonly_cannot_write_and_unknown_tool():
    s, db = make_env(); ro = ToolRegistry(db, "readonly")
    try: ro.call("create_draft_work_order", {"asset_id": "PMP-101"}); assert False
    except PermissionDenied: pass
    try: ToolRegistry(db).call("run_sql", {"q": "select 1"}); assert False
    except MCPError: pass

def test_create_draft_only_draft_validated_and_audited():
    s, db = make_env(); c = InProcessMCPClient(db); rid = c.call("get_asset", asset_id="PMP-106")["current_risk"]["risk_event_id"]
    args = dict(asset_id="PMP-106", risk_event_id=rid, title="Replace bearing", problem_description="vib", priority="HIGH", recommended_steps=["a"],
                required_parts=[{"part_id": "SP-BRG-6309", "quantity": 1}], evidence_references=["SENSOR:vibration"], rationale="r", correlation_id="cid-1")
    r = c.call("create_draft_work_order", **args); assert r["status"] == "DRAFT" and r["validation_result"]["valid"] and r["work_order_id"].startswith("WO-")
    bad = c.call("create_draft_work_order", **{**args, "priority": "SUPER"}); assert bad["status"] == "INVALID"
    bad2 = c.call("create_draft_work_order", **{**args, "asset_id": "NOPE"}); assert bad2["status"] == "INVALID"
    from src.maintenance_app.database import connect; cx = connect(db)
    assert cx.execute("SELECT COUNT(*) FROM audit_log WHERE action='CREATE_DRAFT' AND correlation_id='cid-1'").fetchone()[0] == 1

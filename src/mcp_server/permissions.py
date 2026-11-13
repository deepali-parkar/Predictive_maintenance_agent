"""Explicit per-role tool permissions. The agent can read and create DRAFT work orders - nothing else."""
from src.common.exceptions import PermissionDenied
READ_TOOLS = {"get_asset", "get_sensor_history", "get_risk_events", "get_maintenance_history", "get_asset_work_orders", "check_spares"}
WRITE_TOOLS = {"create_draft_work_order"}
ROLE_TOOLS = {"agent": READ_TOOLS | WRITE_TOOLS, "readonly": set(READ_TOOLS)}
def check(role: str, tool: str) -> None:
    if tool not in ROLE_TOOLS.get(role, set()):
        raise PermissionDenied(f"role '{role}' is not permitted to call '{tool}'")

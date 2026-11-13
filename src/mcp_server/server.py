"""Real MCP server (official Python SDK, FastMCP). Run:  python -m src.mcp_server.server   (stdio transport)."""
from __future__ import annotations
import os
from typing import Optional
from src.mcp_server.tools import ToolRegistry

def build_server():
    from mcp.server.fastmcp import FastMCP
    mcp = FastMCP("sentinel-maintenance"); reg = ToolRegistry(role=os.getenv("SENTINEL_MCP_ROLE", "agent"))

    @mcp.tool()
    def get_asset(asset_id: str) -> dict:
        """Retrieve asset metadata, current risk, latest readings and last maintenance date."""
        return reg.call("get_asset", {"asset_id": asset_id})
    @mcp.tool()
    def get_sensor_history(asset_id: str, start: Optional[str] = None, end: Optional[str] = None, sensors: Optional[list[str]] = None, max_points: int = 300) -> dict:
        """Retrieve (downsampled) sensor readings with summary stats for a date range ('YYYY-MM-DD HH:MM:SS')."""
        return reg.call("get_sensor_history", {"asset_id": asset_id, "start": start, "end": end, "sensors": sensors, "max_points": max_points})
    @mcp.tool()
    def get_risk_events(asset_id: str, risk_event_id: Optional[str] = None, status: Optional[str] = None, limit: int = 5) -> dict:
        """Retrieve risk events including deterministic detection evidence."""
        return reg.call("get_risk_events", {"asset_id": asset_id, "risk_event_id": risk_event_id, "status": status, "limit": limit})
    @mcp.tool()
    def get_maintenance_history(asset_id: str, limit: int = 20) -> dict:
        """Retrieve maintenance records for an asset."""
        return reg.call("get_maintenance_history", {"asset_id": asset_id, "limit": limit})
    @mcp.tool()
    def get_asset_work_orders(asset_id: str, status: Optional[str] = None) -> dict:
        """Retrieve existing work orders for an asset."""
        return reg.call("get_asset_work_orders", {"asset_id": asset_id, "status": status})
    @mcp.tool()
    def check_spares(asset_id: Optional[str] = None, asset_type: Optional[str] = None, part_ids: Optional[list[str]] = None) -> dict:
        """Check spare-part availability and compatibility."""
        return reg.call("check_spares", {"asset_id": asset_id, "asset_type": asset_type, "part_ids": part_ids})
    @mcp.tool()
    def create_draft_work_order(asset_id: str, risk_event_id: Optional[str], title: str, problem_description: str, priority: str,
                                recommended_steps: list[str], required_parts: list[dict], evidence_references: list[str], rationale: str = "",
                                correlation_id: str = "") -> dict:
        """Create a DRAFT work order (never approves or executes). Returns work_order_id, status, created_at, validation_result."""
        return reg.call("create_draft_work_order", {"asset_id": asset_id, "risk_event_id": risk_event_id, "title": title, "problem_description": problem_description,
            "priority": priority, "recommended_steps": recommended_steps, "required_parts": required_parts, "evidence_references": evidence_references,
            "rationale": rationale, "correlation_id": correlation_id, "requested_by": "AGENT:sentinel"})
    return mcp

if __name__ == "__main__":
    build_server().run()

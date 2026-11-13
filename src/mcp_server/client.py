"""MCP clients used by the agent. Both go through the SAME tool registry (same validation, permissions, audit).
 - InProcessMCPClient: dispatches directly to the tool layer (fast; default for Streamlit and tests).
 - StdioMCPClient: spawns `python -m src.mcp_server.server` and talks real MCP over stdio (official SDK)."""
from __future__ import annotations
import asyncio, json, os, sys
from typing import Any, Optional
from src.common.exceptions import MCPError
from src.common.logging_config import get_correlation_id
from src.mcp_server.tools import ToolRegistry

class InProcessMCPClient:
    transport = "inprocess"
    def __init__(self, db_path=None, role: str = "agent"): self.registry = ToolRegistry(db_path, role)
    def call(self, tool: str, **args) -> dict: return self.registry.call(tool, args, correlation_id=get_correlation_id())

class StdioMCPClient:
    transport = "stdio"
    def __init__(self, role: str = "agent", db_path: Optional[str] = None, cwd: Optional[str] = None):
        self.env = {**os.environ, "SENTINEL_MCP_ROLE": role, **({"SENTINEL_DB_PATH": str(db_path)} if db_path else {})}; self.cwd = cwd
    async def _call(self, tool: str, args: dict) -> dict:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        params = StdioServerParameters(command=sys.executable, args=["-m", "src.mcp_server.server"], env=self.env, cwd=self.cwd)
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize(); res = await s.call_tool(tool, {k: v for k, v in args.items() if v is not None})
                if res.isError: raise MCPError(f"{tool}: {res.content[0].text if res.content else 'error'}")
                if res.structuredContent: return res.structuredContent.get("result", res.structuredContent)
                return json.loads(res.content[0].text)
    def call(self, tool: str, **args) -> dict:
        try: return asyncio.run(self._call(tool, args))
        except MCPError: raise
        except Exception as e: raise MCPError(f"MCP stdio call '{tool}' failed: {e}") from e

def make_client(transport: str = "inprocess", db_path=None, role: str = "agent"):
    return StdioMCPClient(role, db_path) if transport == "stdio" else InProcessMCPClient(db_path, role)

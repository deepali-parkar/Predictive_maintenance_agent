"""Agent factory wiring settings -> MCP client + ChromaDB retriever + Azure AI Foundry LLM + router."""
from typing import Optional
from src.agent.graph import SentinelAgent
from src.agent.llm_client import FoundryLLM
from src.agent.model_router import ModelRouter
from src.agent.nodes import AgentDeps
from src.common.config import Settings, get_settings
from src.mcp_server.client import make_client

def build_agent(settings: Optional[Settings] = None, retriever=None, llm=None, mcp=None) -> SentinelAgent:
    s = settings or get_settings()
    from src.rag import build_retriever
    deps = AgentDeps(s, mcp or make_client(s.app["mcp"]["transport"], s.db_path), retriever or build_retriever(s), llm or FoundryLLM(s), ModelRouter(s), str(s.db_path))
    return SentinelAgent(deps)

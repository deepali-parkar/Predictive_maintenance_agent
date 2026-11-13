"""Test helpers: isolated temp environment (own SQLite DB), FakeLLM test double, in-memory vector store."""
import json, os, shutil, tempfile
from pathlib import Path
from src.agent.llm_client import LLMResult
from src.agent.model_router import ModelRouter
from src.agent.nodes import AgentDeps
from src.agent.graph import SentinelAgent
from src.common.config import load_settings
from src.detection.detection_service import run_detection
from src.ingestion.dataset_adapter import ingest_csv, ingest_maintenance, ingest_spares
from src.maintenance_app.database import connect, init_db
from src.mcp_server.client import InProcessMCPClient
from src.rag import index_documents
from src.rag.embeddings import HashingEmbedder
from src.rag.retriever import Retriever
from src.rag.vector_store import InMemoryStore

_TEMPLATE = {}

def make_env(detect=True):
    """Fresh temp DB (copied from a once-built template: synthetic data ingested + detection run)."""
    s = load_settings()
    if "db" not in _TEMPLATE:
        d = Path(tempfile.mkdtemp(prefix="sentinel_tpl_")); db = d / "tpl.db"; c = connect(db); init_db(c); sd = s.path("synthetic")
        ingest_spares(c, sd / "spare_parts.csv"); ingest_csv(c, sd / "sensor_readings.csv", sd / "assets.csv"); ingest_maintenance(c, sd / "maintenance_history.csv")
        s.db_path = db; run_detection(c, settings=s); c.close(); _TEMPLATE["db"] = db
    tmp = Path(tempfile.mkdtemp(prefix="sentinel_t_")); db = tmp / "t.db"; shutil.copy(_TEMPLATE["db"], db)
    s.db_path = db; return s, db

def make_retriever(s):
    st = InMemoryStore(HashingEmbedder()); index_documents(s, st); return Retriever(st, s.detection, 5, 0.25)

class FakeLLM:
    """Deterministic test double standing in for Azure AI Foundry (tests only)."""
    def __init__(self, decision=None, fail_on=None, bad_refs=False, draft_priority=None, draft_parts=None, draft_steps=None, draft_refs=None):
        self.calls = []; self.decision = decision; self.fail_on = fail_on; self.bad_refs = bad_refs; self.draft_priority = draft_priority; self.draft_parts = draft_parts; self.draft_steps = draft_steps; self.draft_refs = draft_refs
    def chat_json(self, deployment, system, user, temperature=0.1, max_tokens=1800):
        d = json.loads(user.split("\n\nYour previous")[0]); self.calls.append((deployment, system[:60]))
        if self.fail_on == deployment: raise RuntimeError("simulated provider failure")
        refs = [r["citation_ref"] for r in d["retrieved_evidence"]]; risk = d["risk"]
        if "explain the risk" in system:
            out = {"likely_failure_mode": d["retrieved_evidence"][0]["failure_mode"] if refs else "UNDETERMINED", "failure_mode_confidence": 0.7 if refs else 0.0,
                   "risk_explanation": "Sensors deviate from baseline " + (refs[0] if refs else "") + (" [DOC:FAKE-1#9]" if self.bad_refs else ""),
                   "supporting_sensor_evidence": ["deviation vs baseline"], "supporting_manual_evidence": [{"citation_ref": r, "summary": "relevant"} for r in refs[:2]] + ([{"citation_ref": "[DOC:FAKE-1#9]", "summary": "invented"}] if self.bad_refs else []),
                   "supporting_maintenance_evidence": [], "uncertainty": "cause not confirmed", "recommended_inspections": ["spectrum analysis"], "evidence_sufficient": bool(refs), "confirmed_fault_acknowledged": False}
        elif "decide whether" in system:
            dec = self.decision or ("INSUFFICIENT_EVIDENCE" if not refs else {"HIGH": "CREATE_DRAFT", "MEDIUM": "INSPECT_FIRST", "LOW": "MONITOR"}[risk["risk_level"]])
            out = {"decision": dec, "rationale": "per evidence", "urgency": "soon", "monitoring_advice": "watch", "confirmed_fault_acknowledged": False}
        else:
            parts = d["available_parts"]; pick = self.draft_parts if self.draft_parts is not None else ([{"part_id": parts[0]["part_id"], "quantity": 1, "notes": ""}] if parts else [])
            out = {"title": "Inspect and repair " + d["asset"]["asset_id"], "problem_description": "Sustained deviation " + risk["reason"][:80], "priority": self.draft_priority or ("HIGH" if risk["risk_level"] == "HIGH" else "MEDIUM"),
                   "recommended_steps": self.draft_steps if self.draft_steps is not None else ["Isolate", "Inspect", "Repair"], "required_parts": pick, "evidence_references": self.draft_refs if self.draft_refs is not None else refs[:2] + ["SENSOR:" + risk["affected_sensors"][0], "RISK:" + risk["risk_event_id"]], "rationale": "supported"}
        return LLMResult(out, 1000, 300, 1300, 0.01, deployment)

def make_agent(s, db, llm=None, retriever=None):
    s.open_deployment, s.frontier_deployment = "open-dep", "frontier-dep"
    deps = AgentDeps(s, InProcessMCPClient(db), retriever or make_retriever(s), llm or FakeLLM(), ModelRouter(s), str(db))
    return SentinelAgent(deps)

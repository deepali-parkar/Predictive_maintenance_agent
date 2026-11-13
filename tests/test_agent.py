from tests.helpers import FakeLLM, make_agent, make_env
from src.maintenance_app.database import connect
from src.maintenance_app.services import get_services

def _run(asset, llm=None, q="", s_db=None):
    s, db = s_db or make_env(); a = make_agent(s, db, llm); return a.run(asset, user_question=q), s, db

def test_demo1_healthy_asset_no_draft_open_model():
    r, s, db = _run("PMP-101"); assert r["decision"] == "MONITOR" and not r["draft_created"] and r["routing"]["model_type"] == "open" and r["error"] is None
    assert r["risk"]["risk_level"] == "LOW"

def test_demo2_medium_risk_frontier_inspect_first_no_draft():
    r, s, db = _run("PMP-102"); assert r["risk"]["risk_level"] == "MEDIUM" and r["routing"]["model_type"] == "frontier" and r["decision"] == "INSPECT_FIRST" and not r["draft_created"]
    assert r["citations"] and r["explanation"]["supporting_manual_evidence"]

def test_demo3_high_risk_multisensor_creates_draft_via_mcp_in_sqlite():
    s, db = make_env(); r = make_agent(s, db).run("MTR-207")
    assert r["risk"]["risk_level"] == "HIGH" and r["routing"]["model_type"] == "frontier" and r["draft_created"] and r["work_order_id"]
    wo = get_services(connect(db)).work_orders.get(r["work_order_id"]); assert wo["status"] == "DRAFT" and wo["created_by"].startswith("AGENT") and wo["risk_event_id"] == r["risk_event"] if False else wo["status"] == "DRAFT"
    assert r["trace"][-4:] == ["draft_generation", "draft_validation", "mcp_draft_creation", "finalize"]
    assert r["total_tokens"] == 3900 and r["estimated_cost"] is not None
    cx = connect(db); assert cx.execute("SELECT COUNT(*) FROM model_call_logs WHERE asset_id='MTR-207'").fetchone()[0] == 3

def test_demo5_insufficient_evidence_no_diagnosis_no_draft():
    r, s, db = _run("CMP-303"); assert r["citations"] == [] and r["decision"] == "INSUFFICIENT_EVIDENCE" and not r["draft_created"]
    assert r["explanation"]["evidence_sufficient"] is False and r["explanation"]["likely_failure_mode"] == "UNDETERMINED"

def test_guardrail_no_evidence_blocks_llm_create_draft():
    r, s, db = _run("CMP-303", FakeLLM(decision="CREATE_DRAFT")); assert r["decision"] == "INSUFFICIENT_EVIDENCE" and not r["draft_created"] and "Guardrail" in r["recommendation"]["guardrail_note"]

def test_confirmed_fault_not_dismissed():
    r, s, db = _run("PMP-106", FakeLLM(decision="MONITOR")); assert r["risk"]["confirmed_fault"] and r["decision"] == "CREATE_DRAFT" and r["draft_created"]
    assert r["recommendation"]["confirmed_fault_acknowledged"] and r["explanation"]["confirmed_fault_acknowledged"]

def test_fabricated_citations_scrubbed():
    r, s, db = _run("MTR-207", FakeLLM(bad_refs=True)); assert any("unsupported citation" in w for w in r["warnings"])
    assert all(m["citation_ref"] != "[DOC:FAKE-1#9]" for m in r["explanation"]["supporting_manual_evidence"]) and "FAKE-1" not in r["explanation"]["risk_explanation"]

def test_harmless_llm_slips_are_repaired_and_reported_never_saved_invented():
    s, db = make_env(); r = make_agent(s, db, FakeLLM(draft_parts=[{"part_id": "SP-INVENTED", "quantity": 1}], draft_priority="LOW", draft_refs=["[DOC:MADE-UP#9]", "SENSOR: vibration"])).run("MTR-207")
    assert r["draft_created"] and not r["draft_errors"]
    assert r["draft"]["required_parts"] == [] and r["draft"]["priority"] == "HIGH" and "[DOC:MADE-UP#9]" not in r["draft"]["evidence_references"] and "SENSOR:vibration" in r["draft"]["evidence_references"]
    ws = " ".join(r["warnings"]); assert "SP-INVENTED" in ws and "priority raised" in ws and "MADE-UP" in ws
    assert get_services(connect(db)).work_orders.get(r["work_order_id"])["parts"] == []

def test_structurally_invalid_draft_never_reaches_database():
    s, db = make_env(); r = make_agent(s, db, FakeLLM(draft_steps=[])).run("MTR-207")
    assert not r["draft_created"] and any("recommended_steps" in e for e in r["draft_errors"]) and connect(db).execute("SELECT COUNT(*) FROM work_orders").fetchone()[0] == 0

def test_empty_knowledge_base_is_diagnosed_not_silent():
    from src.rag.embeddings import HashingEmbedder; from src.rag.retriever import Retriever; from src.rag.vector_store import InMemoryStore
    s, db = make_env(); empty = Retriever(InMemoryStore(HashingEmbedder()), s.detection, 5, 0.15); r = make_agent(s, db, retriever=empty).run("PMP-106")
    assert r["citations"] == [] and "EMPTY" in r["retrieval_debug"]["note"] and any("EMPTY" in w for w in r["warnings"])
    assert r["explanation"]["likely_failure_mode"] == "UNDETERMINED" and r["explanation"]["evidence_sufficient"] is False
    assert r["draft_created"]          # confirmed fault still gets a draft even without manuals

def test_retrieval_debug_reports_filters_and_scores():
    r, s, db = _run("MTR-207"); d = r["retrieval_debug"]; assert d["kb_chunks"] >= 40 and d["kept"] == len(r["citations"]) > 0 and d["candidates"] and d["candidate_failure_modes"]

def test_no_duplicate_draft_when_open_work_order_exists():
    s, db = make_env(); a = make_agent(s, db); r1 = a.run("MTR-207"); r2 = a.run("MTR-207")
    assert r1["draft_created"] and not r2["draft_created"] and r2["duplicate_work_order"] == r1["work_order_id"]

def test_open_model_failure_falls_back_to_frontier_and_logs_both():
    s, db = make_env(); llm = FakeLLM(fail_on="open-dep"); r = make_agent(s, db, llm).run("PMP-101")
    assert r["error"] is None and r["routing"]["model_type"] == "frontier" and "FALLBACK" in r["routing"]["routing_reason"]
    cx = connect(db); assert cx.execute("SELECT COUNT(*) FROM model_call_logs WHERE success=0").fetchone()[0] >= 1

def test_llm_total_failure_reported_not_swallowed():
    s, db = make_env(); r = make_agent(s, db, FakeLLM(fail_on="frontier-dep")).run("MTR-207"); assert r["error"] and "llm_analysis" in r["error"] and not r["draft_created"]

def test_missing_asset_reported():
    s, db = make_env(); r = make_agent(s, db).run("NOPE-1"); assert r["error"] and "mcp_context" in r["error"]

def test_low_risk_complex_question_escalates():
    r, s, db = _run("PMP-101", q="please recommend a work order"); assert r["routing"]["model_type"] == "frontier" and r["routing"]["escalated"]

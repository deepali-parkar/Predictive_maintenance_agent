import json
import pandas as pd
from tests.helpers import FakeLLM, make_agent, make_env
from src.common.config import load_settings
from src.dashboard.data import asset_detections, build_overview_df
from src.evaluation.agent_metrics import agent_eval, governance_eval
from src.evaluation.cost_metrics import routing_report
from src.evaluation.detection_metrics import evaluate
from src.evaluation.rag_metrics import citation_metrics
from src.maintenance_app.database import connect
from src.maintenance_app.services import get_services

def test_overview_df_dynamic_from_sqlite():
    s, db = make_env(); df = build_overview_df(connect(db)); assert len(df) == 20 and set(df.risk_level) == {"LOW", "MEDIUM", "HIGH"}
    assert df[df.asset_id == "PMP-101"].risk_level.iloc[0] == "LOW" and df[df.asset_id == "PMP-106"].risk_level.iloc[0] == "HIGH" and df.latest_readings.str.len().min() > 10

def test_dashboard_graph_data_updates_when_new_readings_ingested():
    from src.ingestion.dataset_adapter import ingest_dataframe
    s, db = make_env(); c = connect(db); before = asset_detections(c, "PMP-101", s.detection)["vibration"].features.index.max()
    df = pd.DataFrame({"asset_id": "PMP-101", "timestamp": pd.date_range("2026-11-09", periods=5, freq="h").astype(str), "vibration_mm_s": [2.5] * 5})
    assert ingest_dataframe(c, df).rows_inserted == 5; assert asset_detections(c, "PMP-101", s.detection)["vibration"].features.index.max() > before

def test_heldout_detection_quality_floor():
    s, db = make_env(); sp = json.loads((s.path("synthetic") / "split.json").read_text()); r = evaluate(connect(db), s.path("synthetic"), s.detection, sp["heldout_assets"])
    assert r["point_level"]["f1"] > 0.85 and r["event_level"]["event_recall"] == 1.0 and r["event_level"]["healthy_false_alarms"] == 0 and r["event_level"]["mean_lead_time_h"] > 0

def test_agent_eval_governance_and_cost_report():
    s, db = make_env(); a = make_agent(s, db); ids = ["PMP-101", "PMP-102", "MTR-207", "CMP-303", "PMP-106"]; res = [a.run(i) for i in ids]
    ev = pd.read_csv(s.path("synthetic") / "degradation_events.csv"); m = agent_eval(res, ev)
    assert m["decision_accuracy"] == 1.0 and m["structured_output_valid"] == 1.0 and m["no_draft_when_unjustified"] == 1.0
    cm = citation_metrics(res); assert cm["citation_correctness"] == 1.0
    g = governance_eval(connect(db)); assert g["approvals_by_agent"] == 0 and g["work_orders_without_create_audit"] == 0
    rep = routing_report(get_services(connect(db)).model_logs.all(), s.routing["pricing_usd_per_1m_tokens"])
    assert rep["savings_usd"] > 0 and rep["routing_distribution"]["open"] >= 1 and rep["routing_distribution"]["frontier"] >= 1

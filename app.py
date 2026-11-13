"""Predictive Maintenance Agent (Streamlit entry point).  Run:  streamlit run app.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pandas as pd
import streamlit as st
from src.common.config import get_settings
from src.common.logging_config import new_correlation_id, set_correlation_id
from src.maintenance_app.database import connect, init_db

st.set_page_config(page_title="Predictive Maintenance", page_icon="🛠️", layout="wide")

@st.cache_resource
def _store():
    from src.rag import build_store
    return build_store(get_settings())

@st.cache_resource
def _agent():
    from src.agent import build_agent
    from src.rag import build_retriever, ensure_indexed
    s = get_settings(); store = _store(); ensure_indexed(s, store)       # self-heal: index manuals + work orders if the knowledge base is empty
    return build_agent(s, retriever=build_retriever(s, store))

class Ctx:
    def __init__(self, conn, planner): self.conn, self.planner, self.settings = conn, planner, get_settings()
    def get_agent(self): return _agent()
    def get_store(self): return _store()
    def reset_agent(self): _agent.clear()

def main():
    s = get_settings(); conn = connect(); init_db(conn); set_correlation_id(new_correlation_id("ui"))
    from src.dashboard import analytics, asset_details, assistant, overview, work_orders
    pages = {"Plant Overview": overview, "Asset Details": asset_details, "AI Assistant": assistant, "Work Orders": work_orders, "Analytics & Audit": analytics}
    st.sidebar.title("🛠️PREDICTIVE MAINTENANCE")
    page = st.sidebar.radio("Navigate", list(pages), key="nav")
    planner = st.sidebar.text_input("Planner name", "planner.demo")
    from src.maintenance_app.services import get_services as _gs
    st.sidebar.metric("Drafts awaiting review", len(_gs(conn).work_orders.list(status="DRAFT")))
    st.sidebar.caption("Only a human planner can approve / edit / reject drafts.")
    if not s.azure_configured: st.sidebar.warning("Azure AI Foundry is not configured (.env). Dashboard works; AI analysis needs credentials.")
    with st.sidebar.expander("Ingest data / run detection"):
        up = st.file_uploader("Sensor CSV (any column naming)", type="csv"); meta = st.file_uploader("Asset metadata CSV (optional)", type="csv")
        if up and st.button("Ingest CSV"):
            from src.ingestion.dataset_adapter import ingest_dataframe
            from src.detection.detection_service import run_detection
            rep = ingest_dataframe(conn, pd.read_csv(up), pd.read_csv(meta) if meta else None, source=up.name); st.json(rep.to_dict(), expanded=False)
            if rep.ok and rep.assets_seen:
                with st.spinner("Running detection on ingested assets..."): res = run_detection(conn, rep.assets_seen)
                st.success(f"Ingested {rep.rows_inserted} readings; assessed {len(res)} asset(s).")
                for r in res:
                    if (r["evidence"] or {}).get("predicted_risk") == "Not assessed": st.warning(f"{r['asset_id']}: {r['risk_level']} is NOT a real assessment - {r['evidence'].get('summary')}")
            elif not rep.ok: st.error("; ".join(rep.errors))
        if st.button("Run detection now"):
            from src.detection.detection_service import run_detection
            with st.spinner("Detecting..."): n = len(run_detection(conn))
            st.success(f"Assessed {n} assets."); st.rerun()
    with st.sidebar.expander("Manage assets (delete)"):
        from src.maintenance_app.services import get_services
        ids = [a["asset_id"] for a in get_services(conn).assets.list()]; victim = st.selectbox("Asset to remove", [""] + ids, key="del_asset")
        ok = st.checkbox("I understand this deletes the asset, its readings, risk events and drafts", key="del_ok")
        if victim and ok and st.button("Delete asset"):
            try: st.success(f"Deleted {victim}: {get_services(conn).asset_admin.delete_asset(victim, planner)}"); st.rerun()
            except Exception as e: st.error(str(e))
    pages[page].render(Ctx(conn, planner))

main()

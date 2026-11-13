"""Page 1: Plant Overview."""
import plotly.express as px
import streamlit as st
from src.dashboard.data import build_overview_df

COLORS = {"LOW": "#2ca02c", "MEDIUM": "#ff9f1c", "HIGH": "#d62728", "UNASSESSED": "#9ca3af"}

def render(ctx):
    st.header("Plant Overview")
    df = build_overview_df(ctx.conn)
    if df.empty: st.info("No assets yet. Run `scripts/ingest_dataset.py` or use **Ingest data** in the sidebar."); return
    c1, c2, c3, c4, c5 = st.columns(5); c5.metric("Not assessed", int((df.risk_level == "UNASSESSED").sum())); c1.metric("Assets", len(df)); c2.metric("High risk", int((df.risk_level == "HIGH").sum())); c3.metric("Medium risk", int((df.risk_level == "MEDIUM").sum())); c4.metric("Low risk", int((df.risk_level == "LOW").sum()))
    f1, f2, f3, f4 = st.columns(4)
    lv = f1.multiselect("Risk level", ["HIGH", "MEDIUM", "LOW", "UNASSESSED"], default=["HIGH", "MEDIUM", "LOW", "UNASSESSED"]); ty = f2.multiselect("Asset type", sorted(df.asset_type.unique()), default=sorted(df.asset_type.unique()))
    cr = f3.multiselect("Criticality", ["CRITICAL", "HIGH", "MEDIUM", "LOW"], default=["CRITICAL", "HIGH", "MEDIUM", "LOW"]); q = f4.text_input("Search (id / name)")
    sort = st.radio("Sort by", ["risk_score", "asset_id", "criticality"], horizontal=True)
    v = df[df.risk_level.isin(lv) & df.asset_type.isin(ty) & df.criticality.isin(cr)]
    if q: v = v[v.asset_id.str.contains(q, case=False) | v.asset_name.str.contains(q, case=False)]
    v = v.sort_values(sort, ascending=(sort != "risk_score"))
    left, right = st.columns([3, 2])
    with right:
        dist = df.groupby(["asset_type", "risk_level"]).size().reset_index(name="assets")
        st.plotly_chart(px.bar(dist, x="asset_type", y="assets", color="risk_level", color_discrete_map=COLORS, title="Risk distribution by asset type"), use_container_width=True)
    with left:
        st.dataframe(v[["asset_id", "asset_name", "asset_type", "criticality", "operating_status", "health", "risk_level", "risk_score", "anomaly_type", "affected_sensors", "latest_readings", "active_risk_events", "last_maintenance"]],
                     use_container_width=True, hide_index=True)
        
    pick = st.selectbox("Open asset", [""] + list(v.asset_id), format_func=lambda x: x or "Select an asset...")
    def _open_asset_details(asset_id: str):
        st.session_state["selected_asset"] = asset_id
        st.session_state["nav"] = "Asset Details"

    if pick:
        st.button(
            "View asset details",
            on_click=_open_asset_details,
            args=(pick,),
        )
       

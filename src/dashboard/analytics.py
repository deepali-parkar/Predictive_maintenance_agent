"""Page 5: model routing / cost analytics and audit log."""
import pandas as pd
import plotly.express as px
import streamlit as st
from src.evaluation.cost_metrics import routing_report
from src.maintenance_app.services import get_services

def render(ctx):
    st.header("Model Routing, Cost & Audit"); svc = get_services(ctx.conn); logs = svc.model_logs.all()
    if logs.empty: st.info("No model calls logged yet. Run an AI analysis first.")
    else:
        rep = routing_report(logs, ctx.settings.routing["pricing_usd_per_1m_tokens"]); c = st.columns(4)
        c[0].metric("LLM calls", rep["calls"]); c[1].metric("Actual cost (USD)", rep["actual_cost_usd"]); c[2].metric("Frontier-only baseline", rep["frontier_only_baseline_usd"]); c[3].metric("Savings", f"{rep['savings_pct']}%" if rep["savings_pct"] is not None else "n/a")
        st.caption(rep["note"]); st.plotly_chart(px.histogram(logs, x="risk_level", color="model_type", title="Routing by risk level"), use_container_width=True)
        st.json(rep["by_model"]); st.dataframe(logs, use_container_width=True, hide_index=True)
    st.subheader("Audit log"); st.dataframe(pd.DataFrame(svc.audit.trail(limit=300)), use_container_width=True, hide_index=True)

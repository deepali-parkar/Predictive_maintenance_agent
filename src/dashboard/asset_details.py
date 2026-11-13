"""Page 2: Asset Details with dynamic Plotly trends."""
from datetime import timedelta
import pandas as pd
import streamlit as st
from src.dashboard.data import asset_detections, date_bounds
from src.dashboard.trends import trend_figure
from src.maintenance_app.services import get_services

CANON = ["vibration", "temperature", "pressure", "current"]

def asset_picker(ctx, key):
    ids = [a["asset_id"] for a in get_services(ctx.conn).assets.list()]
    if not ids: st.info("No assets available."); st.stop()
    cur = st.session_state.get("selected_asset", ids[0]); cur = cur if cur in ids else ids[0]
    sel = st.selectbox("Asset", ids, index=ids.index(cur), key=key); st.session_state["selected_asset"] = sel; return sel

def render(ctx):
    st.header("Asset Details"); svc = get_services(ctx.conn); aid = asset_picker(ctx, "ad_asset"); a = svc.assets.get(aid); risk = svc.risks.current(aid)
    lo, hi = date_bounds(ctx.conn, aid)
    if lo is None: st.warning("No sensor data for this asset."); return
    m = st.columns(5); m[0].metric("Type", a["asset_type"]); m[1].metric("Criticality", a["criticality"]); m[2].metric("Risk", risk["risk_level"] if risk else "n/a", f"score {risk['risk_score']}" if risk else None)
    m[3].metric("Status", a["operating_status"]); m[4].metric("Last service", svc.maintenance.last_service_date(aid) or "-")
    st.caption(f"{a['asset_name']} | {a.get('manufacturer') or '-'} | {a.get('location') or '-'} | installed {a.get('installation_date') or '-'}")
    if risk:
        (st.error if risk["risk_level"] == "HIGH" else st.warning if risk["risk_level"] == "MEDIUM" else st.success)(f"**{risk['risk_level']}** - {risk['evidence'].get('predicted_risk', '')}")
        st.caption("Detected anomaly / predicted risk is NOT a confirmed fault unless marked as such. " + (f"Reason: {risk['evidence'].get('summary', '')}" if risk["evidence"] else ""))
    default_days = ctx.settings.app["dashboard"]["default_days"]
    c1, c2 = st.columns(2); start = c1.date_input("From", max(lo.date(), (hi - timedelta(days=default_days)).date()), min_value=lo.date(), max_value=hi.date())
    end = c2.date_input("To", hi.date(), min_value=lo.date(), max_value=hi.date())
    s_ts, e_ts = pd.Timestamp(start), pd.Timestamp(end) + pd.Timedelta(hours=23, minutes=59)
    dets = asset_detections(ctx.conn, aid, ctx.settings.detection)
    order = [s for s in CANON if s in dets] + [s for s in dets if s not in CANON]
    cols = st.columns(2)
    for i, s in enumerate(order[:4]): cols[i % 2].plotly_chart(trend_figure(s, dets[s], s_ts, e_ts), use_container_width=True, key=f"tr_{aid}_{s}")
    if len(order) > 4:
        with st.expander(f"Additional sensors ({len(order) - 4})"):
            for s in order[4:]: st.plotly_chart(trend_figure(s, dets[s], s_ts, e_ts), use_container_width=True, key=f"tr_{aid}_{s}")
    t1, t2, t3, t4 = st.tabs(["Risk evidence", "Maintenance history", "Risk events", "Work orders"])
    with t1:
        if risk and risk["evidence"].get("sensors"):
            st.dataframe(pd.DataFrame(risk["evidence"]["sensors"])[["sensor_name", "anomaly_type", "window_start", "window_end", "baseline_mean", "current_mean", "deviation_pct", "z_score", "trend_slope_pct_per_day", "threshold_breach", "detection_rule", "sustained_hours", "severity"]], use_container_width=True, hide_index=True)
            st.json({"score_breakdown": risk["evidence"].get("risk_breakdown"), "signal_confidence": risk["evidence"].get("signal_confidence"), "monitoring_urgency": risk["evidence"].get("monitoring_urgency")}, expanded=False)
        else: st.write("No abnormal sensor evidence.")
    with t2: st.dataframe(pd.DataFrame(svc.maintenance.list(aid)), use_container_width=True, hide_index=True)
    with t3: st.dataframe(pd.DataFrame([{k: e[k] for k in ("risk_event_id", "detected_at", "risk_level", "risk_score", "anomaly_type", "status", "confirmed_fault")} for e in svc.risks.list(aid, limit=20)]), use_container_width=True, hide_index=True)
    with t4: st.dataframe(pd.DataFrame([{k: w[k] for k in ("work_order_id", "title", "priority", "status", "created_at")} for w in svc.work_orders.list(aid)]), use_container_width=True, hide_index=True)

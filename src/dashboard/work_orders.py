"""Page 4: Work Order Review (planner approve / edit / reject)."""
import pandas as pd
import streamlit as st
from src.common.exceptions import SentinelError
from src.maintenance_app.services import get_services
from src.review.approval_service import ApprovalService
from src.review.work_order_review import review_bundle

def render(ctx):
    st.header("Work Order Review"); svc = get_services(ctx.conn); planner = ctx.planner
    status = st.selectbox("Status", ["DRAFT", "APPROVED", "REJECTED", "ALL"]); wos = svc.work_orders.list(status=None if status == "ALL" else status)
    if not wos:
        st.info("No work orders in this view. Drafts appear here after you run **AI Assistant -> Explain Risk** on an asset and the agent decides a work order is justified (it needs retrieved evidence, or a confirmed fault).")
        return
    st.dataframe(pd.DataFrame([{k: w[k] for k in ("work_order_id", "asset_id", "title", "priority", "status", "created_by", "created_at")} for w in wos]), use_container_width=True, hide_index=True)
    wid = st.selectbox("Work order", [w["work_order_id"] for w in wos]); b = review_bundle(ctx.conn, wid); wo = b["work_order"]
    st.subheader(f"{wid} - {wo['status']}"); st.caption(f"Asset {wo['asset_id']} | created by {wo['created_by']} at {wo['created_at']} | risk event {wo['risk_event_id']}")
    left, right = st.columns([3, 2])
    with left:
        st.markdown("**Problem**"); st.write(wo["problem_description"]); st.markdown("**Recommended steps**"); [st.write(f"{i}. {s}") for i, s in enumerate(wo["recommended_steps"], 1)]
        st.markdown("**Required parts**"); st.dataframe(pd.DataFrame(wo["parts"]), use_container_width=True, hide_index=True)
        with st.expander("Supporting evidence"):
            st.json(wo["evidence"]);
            if b["risk_event"]: st.write(b["risk_event"]["evidence"].get("summary"))
    with right:
        st.markdown("**Spare parts (compatible)**"); st.dataframe(pd.DataFrame(b["spares"])[["part_id", "part_name", "quantity_available", "reorder_level"]] if b["spares"] else pd.DataFrame(), use_container_width=True, hide_index=True)
    if wo["status"] == "DRAFT":
        st.markdown(f"Acting as planner: **{planner}**"); apr = ApprovalService(ctx.conn)
        with st.form(f"edit_{wid}"):
            title = st.text_input("Title", wo["title"]); prob = st.text_area("Problem description", wo["problem_description"])
            prio = st.selectbox("Priority", ["LOW", "MEDIUM", "HIGH", "URGENT"], index=["LOW", "MEDIUM", "HIGH", "URGENT"].index(wo["priority"]))
            steps = st.text_area("Steps (one per line)", "\n".join(wo["recommended_steps"]))
            parts = st.data_editor(pd.DataFrame(wo["parts"], columns=["part_id", "quantity", "notes"]) if wo["parts"] else pd.DataFrame({"part_id": pd.Series(dtype=str), "quantity": pd.Series(dtype=int), "notes": pd.Series(dtype=str)}), num_rows="dynamic", use_container_width=True)
            reason = st.text_input("Reason / comment (required for rejection)"); a, e, r = st.columns(3)
            do_save, do_app, do_rej = e.form_submit_button("Save edits"), a.form_submit_button("Approve", type="primary"), r.form_submit_button("Reject")
        try:
            changes = {"title": title, "problem_description": prob, "priority": prio, "recommended_steps": [s.strip() for s in steps.splitlines() if s.strip()],
                       "parts": [{"part_id": p.part_id, "quantity": int(p.quantity or 1), "notes": p.notes or ""} for p in parts.itertuples() if p.part_id]}
            if do_save: apr.edit(wid, changes, planner, reason); st.success("Edits saved."); st.rerun()
            if do_app: apr.edit(wid, changes, planner, reason or "edited on approval"); apr.approve(wid, planner, reason); st.success("Approved."); st.rerun()
            if do_rej: apr.reject(wid, planner, reason); st.success("Rejected."); st.rerun()
        except SentinelError as ex: st.error(str(ex))
    else: st.info(f"This work order is {wo['status']} and can no longer be edited." + (f" Rejection reason: {wo['rejection_reason']}" if wo.get("rejection_reason") else ""))
    st.markdown("**Audit trail**"); st.dataframe(pd.DataFrame(b["audit"])[["timestamp", "actor", "action", "reason", "correlation_id"]] if b["audit"] else pd.DataFrame(), use_container_width=True, hide_index=True)

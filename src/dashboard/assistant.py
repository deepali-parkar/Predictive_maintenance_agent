"""Page 3: AI Maintenance Assistant (invokes LangGraph only on explicit user click)."""
import pandas as pd
import streamlit as st
from src.dashboard.asset_details import asset_picker
from src.maintenance_app.services import get_services

def _kb_panel(ctx):
    with st.expander("Knowledge base (ChromaDB: manuals + historical work orders)"):
        try:
            n = ctx.get_store().count(); (st.success if n else st.error)(f"{n} chunks indexed" if n else "Knowledge base is EMPTY - AI analysis cannot cite any evidence until it is indexed.")
        except Exception as e: st.error(f"ChromaDB unavailable: {e}"); n = 0
        if st.button("Index / re-index knowledge base"):
            try:
                from src.rag import index_documents
                with st.spinner("Embedding documents with the Azure embedding deployment..."): st.success(index_documents(ctx.settings, ctx.get_store(), reset=True)); ctx.reset_agent()
            except Exception as e: st.error(f"Indexing failed: {e}")

def _batch(ctx, svc):
    from src.dashboard.data import build_overview_df
    df = build_overview_df(ctx.conn); high = list(df[df.risk_level == "HIGH"].asset_id)
    with st.expander(f"Batch: analyse all HIGH-risk assets ({len(high)})"):
        st.caption("Runs the full agent once per asset (costs tokens). Drafts are created only where the agent decides a work order is justified.")
        if high and st.button(f"Analyse {len(high)} HIGH-risk asset(s)"):
            try: agent = ctx.get_agent()
            except Exception as e: st.error(f"Analysis could not run: {e}"); return
            rows = []; bar = st.progress(0.0)
            for i, a in enumerate(high):
                r = agent.run(a); rows.append({"asset_id": a, "decision": r.get("decision"), "draft": r.get("work_order_id") or "-", "sources": len(r.get("citations", [])), "model": (r.get("routing") or {}).get("model_type"), "error": r.get("error") or ""})
                st.session_state[f"result_{a}"] = r; bar.progress((i + 1) / len(high))
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

def render(ctx):
    st.header("AI Maintenance Assistant"); svc = get_services(ctx.conn); _kb_panel(ctx); aid = asset_picker(ctx, "ai_asset"); risk = svc.risks.current(aid)
    if not risk: st.warning("No risk assessment exists for this asset. Run detection first."); return
    events = svc.risks.list(aid, limit=10); sel = st.selectbox("Risk event", [e["risk_event_id"] for e in events], format_func=lambda x: next(f"{e['risk_event_id']} | {e['risk_level']} {e['risk_score']} | {e['detected_at']} | {e['status']}" for e in events if e["risk_event_id"] == x))
    ev = svc.risks.get(sel); st.markdown(f"**Deterministic risk:** {ev['risk_level']} ({ev['risk_score']}) | {ev['anomaly_type']} | sensors: {', '.join(ev['affected_sensors']) or 'none'}")
    st.caption(ev["evidence"].get("summary", ""))
    q = st.text_area("Optional question / instruction for the analyst", placeholder="e.g. What is the likely cause and should we raise a work order?")
    if st.button("Explain Risk / AI Analysis", type="primary"):
        try:
            agent = ctx.get_agent()
            with st.spinner("Running LangGraph workflow: MCP context -> RAG -> model router -> analysis -> decision..."):
                st.session_state[f"result_{aid}"] = agent.run(aid, sel, q)
        except Exception as e: st.error(f"Analysis could not run: {e}"); return
    _batch(ctx, svc)
    r = st.session_state.get(f"result_{aid}")
    if not r: return
    if r.get("error"): st.error(f"Workflow error: {r['error']}")
    for w in r.get("warnings", []): st.warning(w)
    rt = r.get("routing") or {}; c = st.columns(4); c[0].metric("Model", rt.get("model_type", "-")); c[1].metric("Deployment", rt.get("deployment", "-") or "-")
    c[2].metric("Tokens", r.get("total_tokens") if r.get("total_tokens") is not None else "unavailable"); c[3].metric("Est. cost (USD)", r.get("estimated_cost") if r.get("estimated_cost") is not None else "unavailable")
    st.caption(f"Routing reason: {rt.get('routing_reason', '-')}")
    ex, rec = r.get("explanation"), r.get("recommendation")
    if ex:
        st.subheader("Explanation"); st.write(ex["risk_explanation"])
        a, b = st.columns(2); a.metric("Likely failure mode (suspected)", ex["likely_failure_mode"]); b.metric("Confidence", f"{ex['failure_mode_confidence']:.0%}")
        if not ex["evidence_sufficient"]: st.warning("Reliable technical evidence was not found / is insufficient. No diagnosis is asserted.")
        st.markdown("**Uncertainty:** " + (ex["uncertainty"] or "-"))
        st.markdown("**Sensor evidence**"); [st.write(f"- {x}") for x in ex["supporting_sensor_evidence"]]
        st.markdown("**Manual / historical evidence**"); [st.write(f"- `{m['citation_ref']}` {m['summary']}") for m in ex["supporting_manual_evidence"]]
        st.markdown("**Maintenance-history evidence**"); [st.write(f"- {x}") for x in ex["supporting_maintenance_evidence"]]
        st.markdown("**Suggested inspections**"); [st.write(f"- {x}") for x in ex["recommended_inspections"]]
    if rec:
        st.subheader("Maintenance recommendation"); st.info(f"**{rec['decision']}** - {rec['rationale']}")
        if rec.get("guardrail_note"): st.warning(rec["guardrail_note"])
        if rec.get("monitoring_advice"): st.write("Monitoring: " + rec["monitoring_advice"])
    if r.get("draft_created"):
        st.success(f"Draft work order **{r['work_order_id']}** created (status DRAFT). Open **Work Orders** in the sidebar to edit / approve / reject.")
        d = r.get("draft") or {}; st.markdown(f"**{d.get('title')}** - priority {d.get('priority')}"); st.write(d.get("problem_description")); st.markdown("\n".join(f"{i}. {x}" for i, x in enumerate(d.get("recommended_steps", []), 1)))
        st.caption("Parts: " + (", ".join(f"{p['part_id']} x{p['quantity']}" for p in d.get("required_parts", [])) or "none required") + " | Evidence: " + ", ".join(d.get("evidence_references", [])))
    elif r.get("draft_errors"): st.error("Draft failed validation and was NOT saved: " + "; ".join(r["draft_errors"]))
    elif r.get("duplicate_work_order"): st.info(f"Open work order {r['duplicate_work_order']} already exists for this asset.")
    st.markdown(f"**Next planner action:** {r.get('next_planner_action')}")
    dbg = r.get("retrieval_debug") or {}
    if dbg.get("note") or dbg.get("error"): st.warning(f"Retrieval: {dbg.get('note') or dbg.get('error')}")
    with st.expander("Retrieval diagnostics"): st.json(dbg)
    with st.expander(f"Retrieved sources ({len(r.get('citations', []))})"):
        for cch in r.get("citations", []): st.markdown(f"`{cch['citation_ref']}` **{cch['document_title']}** - {cch['section']} (score {cch['similarity_score']})"); st.caption(cch.get("text", ""))
    with st.expander("Model calls & workflow trace"): st.dataframe(pd.DataFrame(r.get("llm_calls", [])), use_container_width=True); st.write(" -> ".join(r.get("trace", [])))

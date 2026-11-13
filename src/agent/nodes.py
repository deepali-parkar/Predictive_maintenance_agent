"""LangGraph node implementations. Operational data ONLY via MCP; knowledge via ChromaDB retriever; LLM via Azure AI Foundry."""
from __future__ import annotations
import json, time
from dataclasses import dataclass
from functools import wraps
from typing import Any, Optional
import pandas as pd
from src.agent import prompts
from src.agent.llm_client import LLMClient
from src.agent.model_router import ModelRouter, estimate_cost
from src.agent.validators import repair_draft, scrub_explanation, validate_draft
from src.common.config import Settings
from src.common.contracts import MaintenanceExplanation, MaintenanceRecommendation, ModelCallLog, WorkOrderDraft, WorkOrderDraftContent
from src.common.enums import Decision
from src.common.exceptions import ConfigError, LLMError, RetrievalError, SentinelError
from src.common.logging_config import get_logger, set_correlation_id
from src.maintenance_app.database import connect, init_db
from src.maintenance_app.services import ModelLogService

log = get_logger("agent")

@dataclass
class AgentDeps:
    settings: Settings; mcp: Any; retriever: Any; llm: LLMClient; router: ModelRouter; db_path: Optional[str] = None

def _node(name):
    def deco(fn):
        @wraps(fn)
        def run(state):
            t0 = time.time()
            try: upd = fn(state) or {}
            except Exception as e:      # reported to the caller via state['error']; never silently swallowed
                log.error(f"node {name} failed: {e}", exc_info=True); upd = {"error": f"{name}: {type(e).__name__}: {e}"}
            upd["trace"] = list(state.get("trace", [])) + [name]
            log.info("node_done", extra={"ctx": {"node": name, "seconds": round(time.time() - t0, 3)}}); return upd
        return run
    return deco

def _daily_trend(points: list) -> list:
    if not points: return []
    df = pd.DataFrame(points, columns=["t", "v"]); df["d"] = pd.to_datetime(df["t"]).dt.strftime("%m-%d")
    return [[d, round(float(v), 3)] for d, v in df.groupby("d")["v"].mean().tail(8).items()]

def build_nodes(deps: AgentDeps) -> dict:
    S, mcp = deps.settings, deps.mcp

    def log_call(state, routing, operation, res, ok, err=""):
        pt, ct, tt = (res.prompt_tokens, res.completion_tokens, res.total_tokens) if res else (None, None, None)
        entry = ModelCallLog(asset_id=state.get("asset_id"), risk_event_id=state.get("risk_event_id"), risk_level=routing["risk_level"], model_name=routing["deployment"],
            model_type=routing["model_type"], routing_reason=routing["routing_reason"], prompt_tokens=pt, completion_tokens=ct, total_tokens=tt,
            estimated_cost=estimate_cost(S.routing["pricing_usd_per_1m_tokens"], routing["model_type"], pt, ct), operation=operation, success=ok, error_message=err,
            execution_seconds=round(res.seconds, 3) if res else None, correlation_id=state.get("correlation_id", ""))
        c = connect(deps.db_path)
        try: init_db(c); ModelLogService(c).record(entry.model_dump(mode="json"))
        finally: c.close()
        return entry.model_dump(mode="json")

    def invoke(state, operation, system, user, model_cls):
        """LLM call with logging, one schema-repair retry, and open->frontier fallback on provider failure."""
        routing = dict(state["routing"]); calls = []; feedback = ""; cfg = S.routing["llm"]; fell_back = False
        for _ in range(3):
            try: res = deps.llm.chat_json(routing["deployment"], system, user + feedback, cfg["temperature"], cfg["max_completion_tokens"])
            except Exception as e:
                calls.append(log_call(state, routing, operation, None, False, str(e)[:500]))
                if routing["model_type"] == "open" and S.frontier_deployment and not fell_back:
                    fell_back = True; routing.update(model_type="frontier", deployment=S.frontier_deployment, escalated=True,
                                                     routing_reason=routing["routing_reason"] + " | FALLBACK to frontier after open-model failure"); continue
                raise
            try:
                obj = model_cls(**res.data); calls.append(log_call(state, routing, operation, res, True)); return obj, routing, calls
            except ValueError as ve:
                calls.append(log_call(state, routing, operation, res, False, f"schema validation failed: {str(ve)[:300]}"))
                feedback = f"\n\nYour previous JSON failed validation: {str(ve)[:400]}. Return corrected JSON only."
        raise LLMError(f"{operation}: model output failed schema validation")

    def ctx_json(state, extra=None) -> str:
        c = state["evidence_context"]; d = {**c, "retrieved_evidence": [{k: r[k] for k in ("citation_ref", "document_title", "section", "document_type", "failure_mode", "text")} for r in state.get("retrieved", [])]}
        d.update(extra or {}); return json.dumps(d, default=str)

    @_node("initialize")
    def initialize(s):
        if not s.get("asset_id"): raise ValueError("asset_id is required")
        set_correlation_id(s["correlation_id"]); return {"llm_calls": [], "warnings": []}

    @_node("mcp_context")
    def mcp_context(s):
        aid = s["asset_id"]; asset = mcp.call("get_asset", asset_id=aid)
        ev = mcp.call("get_risk_events", asset_id=aid, risk_event_id=s.get("risk_event_id") or None, limit=1)["risk_events"]
        if not ev: raise SentinelError(f"no risk event exists for {aid}; run detection first")
        risk = ev[0]; latest = max((v["timestamp"] for v in asset["latest_readings"].values()), default=None)
        end = latest; start = (pd.Timestamp(latest) - pd.Timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S") if latest else None
        hist = mcp.call("get_sensor_history", asset_id=aid, start=start, end=end, max_points=200)
        return {"asset": asset, "risk_event": risk, "risk_event_id": risk["risk_event_id"], "sensor_history": hist,
                "maintenance_history": mcp.call("get_maintenance_history", asset_id=aid, limit=8)["records"],
                "work_orders": mcp.call("get_asset_work_orders", asset_id=aid)["work_orders"]}

    @_node("evidence_preparation")
    def evidence_preparation(s):
        a, r = s["asset"], s["risk_event"]; ev = r["evidence"]
        sensors = {n: {"unit": d["unit"], **d["summary"], "daily_mean_trend": _daily_trend(d["points"])} for n, d in s["sensor_history"]["sensors"].items()}
        open_wo = [w for w in s["work_orders"] if w["status"] in ("DRAFT", "APPROVED")]
        ctx = {"asset": {k: a[k] for k in ("asset_id", "asset_name", "asset_type", "criticality", "operating_status", "last_service_date", "last_maintenance_date")},
               "risk": {"risk_event_id": r["risk_event_id"], "risk_level": r["risk_level"], "risk_score": r["risk_score"], "anomaly_type": r["anomaly_type"],
                        "confirmed_fault": r["confirmed_fault"], "classification": ev.get("predicted_risk"), "reason": ev.get("summary"), "trend_summary": ev.get("trend_summary"),
                        "signal_confidence": ev.get("signal_confidence"), "score_breakdown": ev.get("risk_breakdown"), "confirmed_fault_record": ev.get("confirmed_fault_record"),
                        "affected_sensors": r["affected_sensors"], "window": [r["window_start"], r["window_end"]]},
               "deterministic_sensor_evidence": ev.get("sensors", []), "recent_sensor_summary_7d": sensors,
               "maintenance_history": s["maintenance_history"], "existing_open_work_orders": open_wo, "user_question": s.get("user_question", "")}
        upd = {"evidence_context": ctx}
        if open_wo: upd["duplicate_work_order"] = open_wo[0]["work_order_id"]
        return upd

    @_node("rag_retrieval")
    def rag_retrieval(s):
        c = s["evidence_context"]; sensors = c["risk"]["affected_sensors"]; w = list(s["warnings"])
        try: res, dbg = deps.retriever.retrieve_with_debug(c["asset"]["asset_type"], sensors, extra_query=s.get("user_question", ""))
        except RetrievalError as e: return {"retrieved": [], "retrieval_debug": {"error": str(e)}, "warnings": w + [f"Knowledge retrieval failed: {e}"]}
        if sensors and not res and dbg.get("note"): w.append(f"No technical evidence retrieved: {dbg['note']}")
        return {"retrieved": [r.model_dump(mode="json") for r in res], "retrieval_debug": dbg, "warnings": w}

    @_node("model_router")
    def model_router(s):
        c = s["evidence_context"]; ev = c["deterministic_sensor_evidence"]
        d = deps.router.decide(c["risk"]["risk_level"], {"n_anomalous_sensors": len(c["risk"]["affected_sensors"]), "directions": [e["direction"] for e in ev],
            "n_failure_modes": len({r["failure_mode"] for r in s["retrieved"]}), "signal_confidence": c["risk"]["signal_confidence"] or 0.0,
            "user_question": s.get("user_question", ""), "criticality": c["asset"]["criticality"], "confirmed_fault": c["risk"]["confirmed_fault"]})
        return {"routing": d.model_dump(mode="json")}

    @_node("llm_analysis")
    def llm_analysis(s):
        from src.common.contracts import RetrievedEvidence
        expl, routing, calls = invoke(s, "evidence_analysis", prompts.ANALYSIS_SYSTEM, ctx_json(s), MaintenanceExplanation)
        expl, w = scrub_explanation(expl, [RetrievedEvidence(**r) for r in s["retrieved"]])
        if s["evidence_context"]["risk"]["confirmed_fault"] and not expl.confirmed_fault_acknowledged: expl = expl.model_copy(update={"confirmed_fault_acknowledged": True})
        return {"explanation": expl.model_dump(mode="json"), "routing": routing, "llm_calls": s["llm_calls"] + calls, "warnings": s["warnings"] + w}

    @_node("maintenance_decision")
    def maintenance_decision(s):
        risk = s["evidence_context"]["risk"]; note = ""
        if risk["anomaly_type"] == "NONE" and not risk["confirmed_fault"]:
            rec = MaintenanceRecommendation(decision="MONITOR", rationale="No abnormal sensor behaviour was detected by the deterministic engine; no maintenance action is indicated.",
                                            urgency=risk.get("monitoring_urgency") or "routine monitoring", monitoring_advice="Continue routine condition monitoring.")
            return {"recommendation": rec.model_dump(mode="json")}
        payload = ctx_json(s, {"analysis": s["explanation"]})
        rec, routing, calls = invoke(s, "maintenance_decision", prompts.DECISION_SYSTEM, payload, MaintenanceRecommendation)
        dec = rec.decision.value; have_evidence = bool(s["retrieved"])
        # --- governance guardrails (deterministic, documented) ---
        if risk["confirmed_fault"]:
            if dec != "CREATE_DRAFT": note = f"Guardrail: a CONFIRMED fault is recorded; decision changed from {dec} to CREATE_DRAFT (fault must not be dismissed for lack of a diagnosis)."; dec = "CREATE_DRAFT"
        elif dec == "CREATE_DRAFT" and not have_evidence:
            note = "Guardrail: no reliable technical evidence was retrieved; draft not justified, decision changed to INSUFFICIENT_EVIDENCE."; dec = "INSUFFICIENT_EVIDENCE"
        upd = {"decision": Decision(dec), "confirmed_fault_acknowledged": rec.confirmed_fault_acknowledged or risk["confirmed_fault"], "guardrail_note": note}
        rec = rec.model_copy(update=upd)
        out = {"recommendation": rec.model_dump(mode="json"), "routing": routing, "llm_calls": s["llm_calls"] + calls}
        if dec == "CREATE_DRAFT" and s.get("duplicate_work_order"):
            out["recommendation"]["guardrail_note"] = (note + " " if note else "") + f"Draft not created: open work order {s['duplicate_work_order']} already exists for this asset."
        return out

    @_node("draft_generation")
    def draft_generation(s):
        parts = mcp.call("check_spares", asset_id=s["asset_id"])["parts"]
        avail = [{"part_id": p["part_id"], "part_name": p["part_name"], "in_stock": p["in_stock"], "quantity_available": p["quantity_available"]} for p in parts if p["compatible"]]
        content, routing, calls = invoke(s, "draft_generation", prompts.DRAFT_SYSTEM, ctx_json(s, {"analysis": s["explanation"], "decision": s["recommendation"], "available_parts": avail}), WorkOrderDraftContent)
        draft = WorkOrderDraft(asset_id=s["asset_id"], risk_event_id=s["risk_event_id"], **content.model_dump(mode="json"))
        return {"draft": draft.model_dump(mode="json"), "available_parts": avail, "routing": routing, "llm_calls": s["llm_calls"] + calls}

    @_node("draft_validation")
    def draft_validation(s):
        d = WorkOrderDraft(**s["draft"]); r = s["evidence_context"]["risk"]
        vctx = {"asset_id": s["asset_id"], "risk_event_id": s["risk_event_id"], "risk_level": r["risk_level"], "retrieved_refs": {x["citation_ref"] for x in s["retrieved"]},
                "affected_sensors": r["affected_sensors"], "available_parts": {p["part_id"] for p in s["available_parts"]}, "known_asset": bool(s.get("asset"))}
        d, notes = repair_draft(d, vctx)
        return {"draft": d.model_dump(mode="json"), "draft_errors": validate_draft(d, vctx), "warnings": s["warnings"] + [f"Draft auto-corrected: {n}" for n in notes]}

    @_node("mcp_draft_creation")
    def mcp_draft_creation(s):
        d = s["draft"]; res = mcp.call("create_draft_work_order", **{**d, "correlation_id": s["correlation_id"], "requested_by": "AGENT:sentinel"})
        if not res.get("validation_result", {}).get("valid", False): return {"draft_errors": res["validation_result"].get("errors", ["rejected by MCP"]), "draft_result": res}
        return {"draft_result": res}

    @_node("finalize")
    def finalize(s):
        rec, calls = s.get("recommendation"), s.get("llm_calls", []); dec = (rec or {}).get("decision")
        created = bool((s.get("draft_result") or {}).get("work_order_id"))
        costs = [c["estimated_cost"] for c in calls]; toks = [c["total_tokens"] for c in calls]
        nxt = ("Review the draft work order in 'Work Order Review' (approve / edit / reject)." if created else
               {"INSPECT_FIRST": "Schedule the recommended inspection, then re-run analysis.", "MONITOR": "Continue monitoring; no work order justified at this time.",
                "INSUFFICIENT_EVIDENCE": "Collect further technical evidence (inspection, additional documentation) before maintenance planning.",
                "CREATE_DRAFT": "Draft not created - see notes."}.get(dec, "Resolve the error and re-run the analysis."))
        result = {"asset_id": s.get("asset_id"), "risk_event_id": s.get("risk_event_id"), "risk": (s.get("evidence_context") or {}).get("risk"), "explanation": s.get("explanation"),
                  "recommendation": rec, "decision": dec, "draft_created": created, "work_order_id": (s.get("draft_result") or {}).get("work_order_id"), "draft": s.get("draft"),
                  "draft_errors": s.get("draft_errors", []), "duplicate_work_order": s.get("duplicate_work_order"), "citations": [{k: r[k] for k in ("citation_ref", "document_title", "section", "document_type", "similarity_score", "text")} for r in s.get("retrieved", [])],
                  "routing": s.get("routing"), "retrieval_debug": s.get("retrieval_debug"), "llm_calls": calls, "total_tokens": None if not toks or any(t is None for t in toks) else sum(toks),
                  "estimated_cost": None if not costs or any(c is None for c in costs) else round(sum(costs), 6), "warnings": s.get("warnings", []),
                  "next_planner_action": nxt, "error": s.get("error"), "trace": s.get("trace", []) + ["finalize"], "correlation_id": s.get("correlation_id")}
        return {"result": result}

    return {"initialize": initialize, "mcp_context": mcp_context, "evidence_preparation": evidence_preparation, "rag_retrieval": rag_retrieval, "model_router": model_router,
            "llm_analysis": llm_analysis, "maintenance_decision": maintenance_decision, "draft_generation": draft_generation, "draft_validation": draft_validation,
            "mcp_draft_creation": mcp_draft_creation, "finalize": finalize}

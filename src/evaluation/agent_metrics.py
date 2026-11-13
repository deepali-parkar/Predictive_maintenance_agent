"""Agent / work-order / governance evaluation against degradation_events.csv expectations."""
from __future__ import annotations
import pandas as pd

def agent_eval(results: list[dict], events: pd.DataFrame) -> dict:
    ev = events.set_index("asset_id"); rows = []
    for r in results:
        aid = r["asset_id"]; acc = ev.loc[aid, "acceptable_decisions"].split("|") if aid in ev.index else ["MONITOR"]
        refs = {c["citation_ref"] for c in r.get("citations", [])}; d = r.get("draft") or {}
        valid_refs = all(x in refs or x.startswith("SENSOR:") or x.startswith("RISK:") for x in d.get("evidence_references", [])) if d else None
        pr = d.get("priority") if d else None; lvl = (r.get("risk") or {}).get("risk_level")
        rows.append({"asset_id": aid, "decision": r.get("decision"), "decision_correct": r.get("decision") in acc, "draft_created": r.get("draft_created"),
                     "draft_appropriate": (r.get("draft_created") == ("CREATE_DRAFT" in acc)) if "CREATE_DRAFT" not in acc or r.get("draft_created") else (r.get("draft_created") is False) or None,
                     "no_draft_when_unjustified": (not r.get("draft_created")) if "CREATE_DRAFT" not in acc else None,
                     "priority_ok": (pr in ("HIGH", "URGENT")) if (d and lvl == "HIGH") else (None if not d else pr != "URGENT"), "draft_evidence_refs_valid": valid_refs,
                     "structured_output_valid": r.get("error") is None and not r.get("draft_errors")})
    df = pd.DataFrame(rows); rate = lambda c: round(float(df[c].dropna().astype(bool).mean()), 3) if df[c].notna().any() else None
    return {"n": len(df), "decision_accuracy": rate("decision_correct"), "no_draft_when_unjustified": rate("no_draft_when_unjustified"), "priority_correct": rate("priority_ok"),
            "draft_evidence_valid": rate("draft_evidence_refs_valid"), "structured_output_valid": rate("structured_output_valid"), "per_asset": rows}

def governance_eval(conn) -> dict:
    q = lambda s: conn.execute(s).fetchone()[0]
    return {"work_orders_total": q("SELECT COUNT(*) FROM work_orders"),
            "agent_created_non_draft_status_violations": q("SELECT COUNT(*) FROM work_orders WHERE created_by LIKE 'AGENT%' AND status='DRAFT' AND approved_by IS NOT NULL"),
            "approvals_by_agent": q("SELECT COUNT(*) FROM work_orders WHERE approved_by LIKE 'AGENT%'"),
            "work_orders_without_create_audit": q("SELECT COUNT(*) FROM work_orders w WHERE NOT EXISTS (SELECT 1 FROM audit_log a WHERE a.entity_type='work_order' AND a.entity_id=w.work_order_id AND a.action='CREATE_DRAFT')"),
            "decided_without_audit": q("SELECT COUNT(*) FROM work_orders w WHERE w.status IN ('APPROVED','REJECTED') AND NOT EXISTS (SELECT 1 FROM audit_log a WHERE a.entity_id=w.work_order_id AND a.action IN ('APPROVE','REJECT'))")}

"""Model-routing evaluation from model_call_logs: usage, cost, savings vs frontier-for-everything baseline."""
from __future__ import annotations
import pandas as pd

def routing_report(logs: pd.DataFrame, pricing: dict) -> dict:
    if logs.empty: return {"calls": 0}
    fr = pricing["frontier"]; known = logs[logs.prompt_tokens.notna() & logs.completion_tokens.notna()].copy()
    known["frontier_cost"] = (known.prompt_tokens * fr["input"] + known.completion_tokens * fr["output"]) / 1e6
    by_model = {}
    for mt, g in logs.groupby("model_type"):
        k = g[g.estimated_cost.notna()]
        by_model[mt] = {"calls": int(len(g)), "failure_rate": round(float((g.success == 0).mean()), 4), "avg_total_tokens": round(float(g.total_tokens.mean()), 1) if g.total_tokens.notna().any() else None,
                        "estimated_cost_usd": round(float(k.estimated_cost.sum()), 6), "usage_unavailable_calls": int(g.estimated_cost.isna().sum())}
    actual = float(known.estimated_cost.sum()); base = float(known.frontier_cost.sum()); ev = logs.dropna(subset=["risk_event_id"])
    return {"calls": int(len(logs)), "routing_distribution": {k: int(v) for k, v in logs.model_type.value_counts().items()},
            "by_risk_level": {k: {m: int(c) for m, c in g.model_type.value_counts().items()} for k, g in logs.groupby("risk_level")}, "by_model": by_model,
            "actual_cost_usd": round(actual, 6), "frontier_only_baseline_usd": round(base, 6), "savings_usd": round(base - actual, 6),
            "savings_pct": round((base - actual) / base * 100, 1) if base else None,
            "cost_per_risk_event_usd": round(actual / ev.risk_event_id.nunique(), 6) if len(ev) and ev.risk_event_id.nunique() else None,
            "note": "Baseline re-prices the SAME logged token counts at frontier rates; calls without reported usage are excluded from cost figures."}

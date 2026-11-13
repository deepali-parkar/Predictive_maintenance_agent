"""RAG evaluation: retrieval relevance vs expected failure mode, insufficient-evidence handling, citation correctness."""
from __future__ import annotations
import pandas as pd

def retrieval_eval(retriever, events: pd.DataFrame, assets: dict, affected: dict) -> dict:
    """events: degradation_events frame (asset_id, failure_mode, acceptable_decisions). affected: asset_id -> sensors flagged by detection."""
    rows = []
    for _, e in events.iterrows():
        a = assets[e.asset_id]; res = retriever.retrieve(a["asset_type"], affected.get(e.asset_id, e.sensors.split(";"))); fm = e.failure_mode
        rel = [r.failure_mode == fm for r in res]; expect_none = e.acceptable_decisions.startswith("INSUFFICIENT_EVIDENCE")
        rows.append({"asset_id": e.asset_id, "expected_failure_mode": fm, "n_retrieved": len(res), "hit": any(rel), "precision": (sum(rel) / len(rel)) if rel else 0.0,
                     "mrr": next((1 / (i + 1) for i, r in enumerate(rel) if r), 0.0), "expect_no_evidence": expect_none, "correct_empty": expect_none and not res})
    d = pd.DataFrame(rows); pos = d[~d.expect_no_evidence]; neg = d[d.expect_no_evidence]
    return {"per_asset": rows, "hit_rate": round(float(pos.hit.mean()), 3) if len(pos) else None, "mean_precision": round(float(pos.precision.mean()), 3) if len(pos) else None,
            "mrr": round(float(pos.mrr.mean()), 3) if len(pos) else None,
            "insufficient_evidence_handling": round(float(neg.correct_empty.mean()), 3) if len(neg) else None}

def citation_metrics(results: list[dict]) -> dict:
    """Citation correctness over agent outputs: every cited manual ref must be a retrieved chunk. Unsupported = refs scrubbed by the validator."""
    cited = valid = removed = covered = n_with_ret = 0
    for r in results:
        refs = {c["citation_ref"] for c in r.get("citations", [])}; ex = r.get("explanation") or {}
        for m in ex.get("supporting_manual_evidence", []): cited += 1; valid += m["citation_ref"] in refs
        for w in r.get("warnings", []):
            if "unsupported citation" in w: removed += int(w.split(" ")[0])
        if refs: n_with_ret += 1; covered += bool(ex.get("supporting_manual_evidence"))
    return {"citations_in_final_output": cited, "citation_correctness": round(valid / cited, 3) if cited else None, "unsupported_citations_stripped": removed,
            "evidence_coverage": round(covered / n_with_ret, 3) if n_with_ret else None}

"""Metadata-filtered similarity retrieval returning structured, citable evidence."""
from __future__ import annotations
from typing import Optional
from src.common.contracts import RetrievedEvidence

class Retriever:
    def __init__(self, store, detection_cfg: dict, top_k: int = 5, min_similarity: float = 0.25):
        self.store, self.hints, self.top_k, self.min_sim = store, detection_cfg.get("failure_mode_hints", {}), top_k, min_similarity
    def failure_modes_for(self, sensors: list[str]) -> list[str]:
        fm: list[str] = []
        for s in sensors:
            for m in self.hints.get(s, []):
                if m not in fm: fm.append(m)
        return fm
    def retrieve(self, asset_type, sensors, failure_modes=None, extra_query="") -> list[RetrievedEvidence]:
        return self.retrieve_with_debug(asset_type, sensors, failure_modes, extra_query)[0]
    def retrieve_with_debug(self, asset_type: str, sensors: list[str], failure_modes: Optional[list[str]] = None, extra_query: str = "") -> tuple[list[RetrievedEvidence], dict]:
        """Filters by asset_type (+ 'general') and candidate failure modes (derived from affected sensors; a retrieval filter, not a diagnosis).
        No unfiltered fallback: if nothing relevant exists, an EMPTY list is returned and the agent must state evidence is insufficient."""
        fms = failure_modes or self.failure_modes_for(sensors)
        dbg = {"kb_chunks": self.store.count(), "min_similarity": self.min_sim, "asset_type": asset_type, "candidate_failure_modes": fms, "candidates": [], "kept": 0, "note": ""}
        if not sensors and not fms: dbg["note"] = "no abnormal sensors - retrieval skipped"; return [], dbg
        if dbg["kb_chunks"] == 0: dbg["note"] = "knowledge base is EMPTY - index the manuals and work orders"; return [], dbg
        where = {"asset_type": [asset_type, "general"]}
        if fms: where["failure_mode"] = fms
        q = f"{asset_type} {' '.join(sensors)} abnormal symptoms causes inspection corrective action {' '.join(fms)} {extra_query}".strip()
        out = []; hits = self.store.query(q, self.top_k, where)
        dbg["candidates"] = [{"ref": h["metadata"]["citation_ref"], "score": round(h["score"], 3)} for h in hits]
        if not hits: dbg["note"] = f"no documents exist for asset_type in {where['asset_type']} and failure modes {fms}"
        for h in hits:
            if h["score"] < self.min_sim: continue
            m = h["metadata"]
            out.append(RetrievedEvidence(source_id=h["id"], citation_ref=m["citation_ref"], document_id=m["document_id"], document_title=m["document_title"],
                document_type=m["document_type"], section=m.get("section", ""), text=h["text"], asset_type=m.get("asset_type", ""),
                failure_mode=m.get("failure_mode", ""), page_number=m.get("page_number") or None, source_file=m.get("source_file", ""), similarity_score=round(h["score"], 4)))
        dbg["kept"] = len(out)
        if hits and not out: dbg["note"] = f"{len(hits)} candidate(s) found but all below min_similarity {self.min_sim} (best {max(h['score'] for h in hits):.3f})"
        return out, dbg

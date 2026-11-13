"""Deterministic validation of LLM outputs before they reach downstream consumers or the database."""
from __future__ import annotations
import re
from src.common.enums import Priority
from src.common.contracts import MaintenanceExplanation, RetrievedEvidence, WorkOrderDraft
from src.rag.citations import REF_RE, validate_citations

def scrub_explanation(expl: MaintenanceExplanation, retrieved: list[RetrievedEvidence]) -> tuple[MaintenanceExplanation, list[str]]:
    """Remove citations that are not actual retrieved chunks (anti-fabrication). Returns (clean, warnings)."""
    known = {r.citation_ref for r in retrieved}; removed: list[str] = []
    def clean(t: str) -> str:
        def sub(m):
            if m.group(0) in known: return m.group(0)
            removed.append(m.group(0)); return "[unverified citation removed]"
        return REF_RE.sub(sub, t or "")
    keep = []
    for m in expl.supporting_manual_evidence:
        if m.citation_ref in known: keep.append(m.model_copy(update={"summary": clean(m.summary)}))
        else: removed.append(m.citation_ref)
    upd = {"supporting_manual_evidence": keep, "risk_explanation": clean(expl.risk_explanation), "uncertainty": clean(expl.uncertainty),
           "supporting_sensor_evidence": [clean(x) for x in expl.supporting_sensor_evidence],
           "supporting_maintenance_evidence": [clean(x) for x in expl.supporting_maintenance_evidence],
           "recommended_inspections": [clean(x) for x in expl.recommended_inspections]}
    if not retrieved: upd.update(evidence_sufficient=False, likely_failure_mode="UNDETERMINED", failure_mode_confidence=0.0)
    elif not keep and expl.evidence_sufficient: upd["evidence_sufficient"] = False
    w = [f"{len(removed)} unsupported citation(s) removed from AI output: {sorted(set(removed))}"] if removed else []
    return expl.model_copy(update=upd), w

def repair_draft(d: WorkOrderDraft, ctx: dict) -> tuple[WorkOrderDraft, list[str]]:
    """Deterministically fixes harmless LLM slips (reference formatting, unknown refs/parts, too-low priority) and reports every change.
    Fabricated parts/references are REMOVED (never saved); structural problems (no steps, no title) are left for validate_draft to reject."""
    notes = []; sensors = set(ctx["affected_sensors"]); rid = f"RISK:{ctx['risk_event_id']}"
    refs, seen = [], set()
    for r in d.evidence_references:
        r2 = re.sub(r"^(SENSOR|RISK):\s+", r"\1:", r.strip())
        ok = r2 in ctx["retrieved_refs"] or (r2.startswith("SENSOR:") and r2[7:] in sensors) or r2 == rid
        if ok and r2 not in seen: refs.append(r2); seen.add(r2)
        elif not ok: notes.append(f"removed unverifiable evidence reference '{r}'")
    if not refs:
        refs = [rid] + [f"SENSOR:{x}" for x in sorted(sensors)]; notes.append("no valid evidence reference supplied; attached deterministic detection evidence")
    parts = []
    for p in d.required_parts:
        if p.part_id in ctx["available_parts"]: parts.append(p)
        else: notes.append(f"removed part '{p.part_id}' (not in the compatible spare-parts list)")
    pr = d.priority.value if hasattr(d.priority, "value") else str(d.priority); lvl = ctx["risk_level"]
    if lvl == "HIGH" and pr in ("LOW", "MEDIUM"): notes.append(f"priority raised {pr} -> HIGH (HIGH risk)"); pr = "HIGH"
    if lvl == "LOW" and pr == "URGENT": notes.append("priority lowered URGENT -> MEDIUM (LOW risk)"); pr = "MEDIUM"
    return d.model_copy(update={"evidence_references": refs, "required_parts": parts, "priority": Priority(pr)}), notes

def validate_draft(d: WorkOrderDraft, ctx: dict) -> list[str]:
    """ctx: asset_id, risk_event_id, risk_level, retrieved_refs(set), affected_sensors, available_parts{part_id:...}, known_asset(bool)."""
    errs = []
    if d.asset_id != ctx["asset_id"]: errs.append("asset_id does not match the analysed asset")
    if not ctx.get("known_asset", True): errs.append("asset does not exist")
    if d.risk_event_id != ctx["risk_event_id"]: errs.append("risk_event_id does not match the analysed risk event")
    if not d.title.strip() or not d.problem_description.strip(): errs.append("title and problem_description are required")
    if not d.recommended_steps: errs.append("recommended_steps is empty")
    lvl = ctx["risk_level"]; pr = d.priority.value if hasattr(d.priority, "value") else str(d.priority)
    if lvl == "HIGH" and pr not in ("HIGH", "URGENT"): errs.append("priority too low for HIGH risk")
    if lvl == "LOW" and pr == "URGENT": errs.append("priority URGENT inconsistent with LOW risk")
    if not d.evidence_references: errs.append("evidence_references is empty")
    for ref in d.evidence_references:
        ok = ref in ctx["retrieved_refs"] or (ref.startswith("SENSOR:") and ref[7:] in ctx["affected_sensors"]) or ref == f"RISK:{ctx['risk_event_id']}"
        if not ok: errs.append(f"evidence reference not found in retrieved/available evidence: {ref}")
    for p in d.required_parts:
        if p.part_id not in ctx["available_parts"]: errs.append(f"part {p.part_id} is not in the compatible spare-parts list (do not invent parts)")
    return errs

"""Citation references and validation against actually-retrieved chunks."""
import re
from src.common.contracts import RetrievedEvidence
REF_RE = re.compile(r"\[DOC:[A-Za-z0-9_.\-]+#\d+(?:-\d+)?\]")

def make_ref(document_id: str, section_idx: int, part: int = 0) -> str:
    return f"[DOC:{document_id}#{section_idx}{f'-{part}' if part else ''}]"

def extract_refs(text: str) -> list[str]: return REF_RE.findall(text or "")

def validate_citations(refs: list[str], retrieved: list[RetrievedEvidence]) -> tuple[list[str], list[str]]:
    """Returns (valid, invalid). A citation is valid ONLY if it equals the citation_ref of a retrieved chunk."""
    known = {r.citation_ref for r in retrieved}
    return [r for r in refs if r in known], [r for r in refs if r not in known]

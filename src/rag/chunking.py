"""Section-aware chunking with metadata. One chunk per section; long sections are split on sentence boundaries."""
from __future__ import annotations
import re
from src.rag.citations import make_ref
from src.rag.document_loader import Document

def _split(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars: return [text]
    out, cur = [], ""
    for s in re.split(r"(?<=[.!?])\s+", text):
        if cur and len(cur) + len(s) + 1 > max_chars: out.append(cur); cur = s
        else: cur = f"{cur} {s}".strip()
    return out + ([cur] if cur else [])

def chunk_document(doc: Document, max_chars: int = 900) -> list[dict]:
    chunks = []
    for i, (head, text, page) in enumerate(doc.sections, 1):
        for k, piece in enumerate(_split(text, max_chars)):
            ref = make_ref(doc.document_id, i, k)
            chunks.append({"id": ref.strip("[]").replace("DOC:", ""), "text": piece, "embed_text": f"{doc.document_title} - {head}. {doc.asset_type} {doc.failure_mode}. {piece}",
                "metadata": {"document_id": doc.document_id, "document_type": doc.document_type, "document_title": doc.document_title, "asset_type": doc.asset_type,
                             "failure_mode": doc.failure_mode, "section": head, "page_number": page or 0, "source_file": doc.source_file, "citation_ref": ref}})
    return chunks

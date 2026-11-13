"""Load maintenance manuals (Markdown + front matter) and historical work orders (JSON)."""
from __future__ import annotations
import json, re
from dataclasses import dataclass, field
from pathlib import Path
import yaml
from src.common.exceptions import RetrievalError

@dataclass
class Document:
    document_id: str; document_type: str; document_title: str; asset_type: str; failure_mode: str; source_file: str
    sections: list = field(default_factory=list)     # [(heading, text, page_number|None)]

def load_manual(path: Path) -> Document:
    raw = path.read_text(encoding="utf-8"); m = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.S)
    if not m: raise RetrievalError(f"{path.name}: missing front matter")
    meta = yaml.safe_load(m.group(1)); doc = Document(meta["document_id"], meta.get("document_type", "manual"), meta["document_title"],
                                                      meta.get("asset_type", "general"), meta.get("failure_mode", "GENERAL"), meta.get("source_file", path.name))
    for block in re.split(r"^## ", m.group(2), flags=re.M)[1:]:
        head, _, body = block.partition("\n"); pg = re.search(r"<!--\s*page:\s*(\d+)\s*-->", body)
        text = re.sub(r"<!--.*?-->", "", body).strip()
        if text: doc.sections.append((head.strip(), text, int(pg.group(1)) if pg else None))
    return doc

def load_historical(path: Path) -> Document:
    d = json.loads(path.read_text(encoding="utf-8"))
    text = (f"Problem: {d['problem_description']} Actions taken: {'; '.join(d.get('actions_taken', []))}. "
            f"Parts used: {', '.join(d.get('parts_used', [])) or 'none'}. Outcome: {d.get('outcome', '')}")
    return Document(d["document_id"], "historical_work_order", d["document_title"], d["asset_type"], d["failure_mode"], path.name, [("Work order record", text, None)])

def load_all(manuals_dir: Path, wo_dir: Path) -> list[Document]:
    docs = [load_manual(p) for p in sorted(Path(manuals_dir).glob("*.md"))] + [load_historical(p) for p in sorted(Path(wo_dir).glob("*.json"))]
    if not docs: raise RetrievalError(f"no documents found in {manuals_dir} / {wo_dir}")
    return docs

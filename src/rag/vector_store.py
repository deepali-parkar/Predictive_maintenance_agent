"""ChromaDB persistent vector store (data/chroma). InMemoryStore mirrors the API for unit tests only."""
from __future__ import annotations
import json, threading
from pathlib import Path
from typing import Optional
import numpy as np
from src.common.exceptions import RetrievalError

_LOCK = threading.RLock()

def _match(md: dict, where: Optional[dict]) -> bool:
    if not where: return True
    return all(md.get(k) in v for k, v in where.items())

def _chroma_where(where: Optional[dict]):
    if not where: return None
    conds = [{k: {"$in": list(v)}} for k, v in where.items()]
    return conds[0] if len(conds) == 1 else {"$and": conds}

class ChromaStore:
    """Persistent ChromaDB store. Records which embedder built the index and refuses to query with a different one
    (a dimension mismatch can crash some Chroma builds natively). Access is serialised with a lock."""
    def __init__(self, path, embedder, collection: str = "maintenance_knowledge"):
        try:
            import chromadb
            self.client = chromadb.PersistentClient(path=str(path))
            self.col = self.client.get_or_create_collection(collection, metadata={"hnsw:space": "cosine"})
        except Exception as e: raise RetrievalError(f"ChromaDB unavailable: {e}") from e
        self.embedder = embedder; self.collection = collection; self.marker = Path(path) / "embedder.json"
    def _marker(self):
        return json.loads(self.marker.read_text()) if self.marker.exists() else None
    def compatible(self) -> bool:
        """True if the stored index was built with the current embedder (name + dimension)."""
        m = self._marker()
        return bool(m) and m["name"] == self.embedder.name and m["dim"] == len(self.embedder.embed(["probe"])[0])
    def _check(self, dim: int):
        m = self._marker()
        if m and (m["dim"] != dim or m["name"] != self.embedder.name):
            raise RetrievalError(f"Index was built with '{m['name']}' (dim {m['dim']}) but queries use '{self.embedder.name}' (dim {dim}). Re-index the knowledge base.")
    def upsert(self, chunks: list[dict]) -> int:
        if not chunks: return 0
        embs = self.embedder.embed([c["embed_text"] for c in chunks]); self._check(len(embs[0]))
        with _LOCK:
            try: self.col.upsert(ids=[c["id"] for c in chunks], documents=[c["text"] for c in chunks], metadatas=[c["metadata"] for c in chunks], embeddings=embs)
            except Exception as e: raise RetrievalError(f"ChromaDB upsert failed: {e}") from e
        self.marker.write_text(json.dumps({"name": self.embedder.name, "dim": len(embs[0])})); return len(chunks)
    def query(self, text: str, top_k: int = 5, where: Optional[dict] = None) -> list[dict]:
        n = self.count()
        if n == 0: return []
        q = self.embedder.embed([text]); self._check(len(q[0]))
        with _LOCK:
            try: r = self.col.query(query_embeddings=q, n_results=min(top_k, n), where=_chroma_where(where))
            except Exception as e: raise RetrievalError(f"ChromaDB query failed: {e}") from e
        return [{"id": i, "text": d, "metadata": m, "score": 1.0 - float(dist)} for i, d, m, dist in zip(r["ids"][0], r["documents"][0], r["metadatas"][0], r["distances"][0])]
    def count(self) -> int:
        with _LOCK: return self.col.count()
    def reset(self) -> None:
        with _LOCK:
            self.client.delete_collection(self.collection); self.col = self.client.get_or_create_collection(self.collection, metadata={"hnsw:space": "cosine"})
        self.marker.unlink(missing_ok=True)

class InMemoryStore:
    """Test double with identical API (cosine similarity). Not used in production."""
    def __init__(self, embedder): self.embedder = embedder; self.items: dict = {}
    def upsert(self, chunks):
        for c, e in zip(chunks, self.embedder.embed([c["embed_text"] for c in chunks])): self.items[c["id"]] = (c, np.array(e))
        return len(chunks)
    def query(self, text, top_k=5, where=None):
        q = np.array(self.embedder.embed([text])[0]); hits = []
        for c, e in self.items.values():
            if _match(c["metadata"], where): hits.append({"id": c["id"], "text": c["text"], "metadata": c["metadata"], "score": float(q @ e / (np.linalg.norm(q) * np.linalg.norm(e) + 1e-12))})
        return sorted(hits, key=lambda h: -h["score"])[:top_k]
    def count(self): return len(self.items)
    def reset(self): self.items = {}
    def compatible(self) -> bool: return True

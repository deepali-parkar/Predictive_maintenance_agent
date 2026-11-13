"""RAG pipeline: loader -> chunking -> embeddings -> ChromaDB -> retriever -> citations."""
from src.common.config import Settings
from src.rag.chunking import chunk_document
from src.rag.document_loader import load_all
from src.rag.embeddings import get_embedder
from src.rag.retriever import Retriever
from src.rag.vector_store import ChromaStore

def build_store(s: Settings, embedder=None) -> ChromaStore:
    return ChromaStore(s.chroma_path, embedder or get_embedder(s), s.app["rag"]["collection"])

def build_retriever(s: Settings, store=None) -> Retriever:
    r = s.app["rag"]; return Retriever(store or build_store(s), s.detection, r["top_k"], r["min_similarity"])

def index_documents(s: Settings, store, reset: bool = False) -> dict:
    if reset: store.reset()
    docs = load_all(s.path("manuals"), s.path("historical_work_orders")); n = 0
    for d in docs: n += store.upsert(chunk_document(d))
    return {"documents": len(docs), "chunks": n, "collection_count": store.count()}

def ensure_indexed(s: Settings, store) -> dict:
    """Self-healing: (re)build the knowledge base if it is empty or was built with a different embedding model."""
    if store.count() > 0 and store.compatible(): return {"indexed": False, "collection_count": store.count()}
    return {"indexed": True, **index_documents(s, store, reset=True)}

from tests.helpers import make_retriever, make_env
from src.common.contracts import RetrievedEvidence
from src.rag.chunking import chunk_document
from src.rag.document_loader import load_all
from src.rag.citations import extract_refs, validate_citations

def test_documents_chunked_with_metadata():
    s, _ = make_env(); docs = load_all(s.path("manuals"), s.path("historical_work_orders")); assert len(docs) >= 17
    ch = chunk_document(docs[0]); m = ch[0]["metadata"]
    for k in ("document_id", "document_type", "document_title", "asset_type", "failure_mode", "section", "source_file", "citation_ref"): assert k in m
    assert m["page_number"] >= 1

def test_retrieval_filters_and_returns_citable_evidence():
    s, _ = make_env(); r = make_retriever(s); res = r.retrieve("pump", ["vibration"])
    assert res and all(e.asset_type in ("pump", "general") and e.failure_mode in ("BEARING_WEAR", "MISALIGNMENT_IMBALANCE") for e in res)
    assert all(e.citation_ref.startswith("[DOC:") and e.similarity_score >= 0.25 for e in res)

def test_no_evidence_returns_empty_not_irrelevant_fallback():
    s, _ = make_env(); assert make_retriever(s).retrieve("compressor", ["current"]) == []

def test_citation_validation():
    s, _ = make_env(); res = make_retriever(s).retrieve("pump", ["vibration"]); good = res[0].citation_ref
    v, inv = validate_citations([good, "[DOC:FAKE#1]"], res); assert v == [good] and inv == ["[DOC:FAKE#1]"]
    assert extract_refs(f"see {good} and [DOC:X#2]") == [good, "[DOC:X#2]"]


def _chroma_store(dim=256):
    import tempfile
    from src.rag.embeddings import HashingEmbedder; from src.rag.vector_store import ChromaStore
    return ChromaStore(tempfile.mkdtemp(prefix="chroma_t_"), HashingEmbedder(dim), "kb_test")

def test_chroma_store_index_retrieve_and_self_heal():
    try: import chromadb  # noqa
    except ImportError: return
    from src.rag import ensure_indexed, index_documents; from src.rag.retriever import Retriever
    s, _ = make_env(); st = _chroma_store(); assert st.count() == 0
    r = Retriever(st, s.detection, 5, 0.15); ev, dbg = r.retrieve_with_debug("pump", ["vibration"]); assert ev == [] and "EMPTY" in dbg["note"]
    out = ensure_indexed(s, st); assert out["indexed"] and st.count() >= 40
    ev, dbg = r.retrieve_with_debug("pump", ["vibration"]); assert ev and dbg["kept"] == len(ev) and all(e.asset_type in ("pump", "general") for e in ev)
    assert r.retrieve("compressor", ["current"]) == []
    assert ensure_indexed(s, st)["indexed"] is False

def test_chroma_embedder_change_detected_and_rebuilt_not_crashed():
    try: import chromadb  # noqa
    except ImportError: return
    from src.common.exceptions import RetrievalError; from src.rag import ensure_indexed, index_documents; from src.rag.embeddings import HashingEmbedder
    s, _ = make_env(); st = _chroma_store(256); index_documents(s, st, reset=True); assert st.compatible()
    st.embedder = HashingEmbedder(128); assert not st.compatible()
    try: st.query("pump vibration", 3); assert False
    except RetrievalError as e: assert "Re-index" in str(e)
    assert ensure_indexed(s, st)["indexed"] and st.compatible() and st.query("pump vibration", 3)

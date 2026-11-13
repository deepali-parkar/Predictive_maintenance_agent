"""Retrieval relevance + insufficient-evidence handling. Uses Azure embeddings + ChromaDB (index first with ingest_documents.py).
--offline-test uses a lexical hashing embedder + in-memory store: wiring check only, NOT representative of semantic retrieval."""
import argparse, json, _bootstrap  # noqa
from pathlib import Path
import pandas as pd
from src.common.config import get_settings
from src.evaluation.rag_metrics import retrieval_eval
from src.maintenance_app.database import connect, init_db
from src.maintenance_app.services import get_services
from src.rag.retriever import Retriever

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--offline-test", action="store_true"); a = ap.parse_args(); s = get_settings()
    if a.offline_test:
        from src.rag import index_documents
        from src.rag.embeddings import HashingEmbedder
        from src.rag.vector_store import InMemoryStore
        store = InMemoryStore(HashingEmbedder()); index_documents(s, store); print("** OFFLINE TEST MODE (lexical embeddings) **")
    else:
        from src.rag import build_store
        store = build_store(s)
    r = s.app["rag"]; ret = Retriever(store, s.detection, r["top_k"], r["min_similarity"])
    c = connect(); init_db(c); svc = get_services(c); events = pd.read_csv(s.path("synthetic") / "degradation_events.csv")
    assets = {x["asset_id"]: x for x in svc.assets.list()}; affected = {e.asset_id: (svc.risks.current(e.asset_id) or {}).get("affected_sensors", []) for e in events.itertuples()}
    res = retrieval_eval(ret, events, assets, affected); Path("reports").mkdir(exist_ok=True); Path("reports/rag_eval.json").write_text(json.dumps(res, indent=2))
    print({k: v for k, v in res.items() if k != "per_asset"})

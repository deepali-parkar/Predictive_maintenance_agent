"""Chunk, embed (Azure AI Foundry embedding deployment) and index manuals + historical work orders into ChromaDB."""
import argparse, json, _bootstrap  # noqa
from src.common.config import get_settings
from src.rag import build_store, index_documents

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--reset", action="store_true"); a = ap.parse_args(); s = get_settings()
    print(json.dumps(index_documents(s, build_store(s), a.reset), indent=2))

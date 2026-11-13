"""LIVE connectivity check for the three Azure AI Foundry deployments (needs your credentials in .env)."""
import _bootstrap  # noqa
from src.common.config import get_settings
from src.agent.llm_client import FoundryLLM
from src.rag.embeddings import AzureEmbedder

if __name__ == "__main__":
    s = get_settings(); ok = True
    for name, dep in (("open", s.open_deployment), ("frontier", s.frontier_deployment)):
        try:
            r = FoundryLLM(s).chat_json(dep, "Reply with JSON only.", 'Return {"ok": true}.', 0.0, 50)
            print(f"[OK ] {name:8} deployment='{dep}' json={r.data} tokens={r.total_tokens}")
        except Exception as e: ok = False; print(f"[FAIL] {name:8} deployment='{dep}': {e}")
    try: v = AzureEmbedder(s).embed(["bearing wear"]); print(f"[OK ] embedding deployment='{s.embedding_deployment}' dim={len(v[0])}")
    except Exception as e: ok = False; print(f"[FAIL] embedding deployment='{s.embedding_deployment}': {e}")
    raise SystemExit(0 if ok else 1)

"""Embeddings via Azure AI Foundry embedding deployment. A hashing embedder exists ONLY for offline tests/demos."""
from __future__ import annotations
import hashlib, os, re
from typing import Protocol
import numpy as np
from src.common.config import Settings
from src.common.exceptions import ConfigError, LLMError
from src.common.logging_config import get_logger

log = get_logger("embeddings")
class Embedder(Protocol):
    name: str
    def embed(self, texts: list[str]) -> list[list[float]]: ...

class AzureEmbedder:
    def __init__(self, s: Settings):
        if not (s.azure_configured and s.embedding_deployment): raise ConfigError("Azure embedding deployment not configured (see .env.example)")
        from openai import AzureOpenAI
        self.client = AzureOpenAI(azure_endpoint=s.endpoint, api_key=s.api_key, api_version=s.api_version); self.name = s.embedding_deployment
    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        try:
            for i in range(0, len(texts), 16):
                r = self.client.embeddings.create(model=self.name, input=texts[i:i + 16]); out += [d.embedding for d in r.data]
        except Exception as e: raise LLMError(f"Azure embedding call failed: {e}") from e
        return out

class HashingEmbedder:
    """OFFLINE TEST ONLY: lexical hashing, not semantic. Enabled with EMBEDDINGS_BACKEND=local_hash."""
    name = "local-hash-256"
    def __init__(self, dim: int = 256): self.dim = dim
    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            v = np.zeros(self.dim); toks = re.findall(r"[a-z0-9]+", t.lower())
            for w in toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:])]:
                v[int(hashlib.md5(w.encode()).hexdigest(), 16) % self.dim] += 1.0
            n = np.linalg.norm(v); out.append((v / n if n else v).tolist())
        return out

def get_embedder(s: Settings) -> Embedder:
    if os.getenv("EMBEDDINGS_BACKEND", "azure").lower() == "local_hash":
        log.warning("USING OFFLINE HASHING EMBEDDER - lexical only, for tests/demos without Azure"); return HashingEmbedder()
    return AzureEmbedder(s)

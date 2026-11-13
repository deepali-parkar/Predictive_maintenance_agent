"""Configuration loader: YAML files in config/ + environment (.env). No secrets are stored in code."""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]

def _load(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

@dataclass
class Settings:
    root: Path
    app: dict
    detection: dict
    risk: dict
    routing: dict
    sensor_mapping: dict
    endpoint: str = ""
    api_key: str = ""
    api_version: str = "2024-10-21"
    open_deployment: str = ""
    frontier_deployment: str = ""
    embedding_deployment: str = ""
    open_endpoint: str = ""
    open_api_key: str = ""
    db_path: Path = field(default_factory=Path)
    chroma_path: Path = field(default_factory=Path)

    def path(self, key: str) -> Path:
        p = Path(self.app["paths"][key]); return p if p.is_absolute() else self.root / p

    @property
    def azure_configured(self) -> bool:
        return bool(self.endpoint and self.api_key)

    def deployment_for(self, model_type: str) -> str:
        d = self.open_deployment if model_type == "open" else self.frontier_deployment
        return d

def load_settings(root: Optional[Path] = None, config_dir: Optional[Path] = None) -> Settings:
    root = Path(root or os.getenv("SENTINEL_ROOT") or ROOT)
    load_dotenv(root / ".env", override=False)
    cdir = Path(config_dir or os.getenv("SENTINEL_CONFIG_DIR") or (root / "config"))
    s = Settings(root=root, app=_load(cdir / "app_config.yaml"), detection=_load(cdir / "detection_config.yaml"),
                 risk=_load(cdir / "risk_config.yaml"), routing=_load(cdir / "model_routing.yaml"),
                 sensor_mapping=_load(cdir / "sensor_mapping.yaml"))
    g = os.getenv
    s.endpoint = g("AZURE_AI_FOUNDRY_ENDPOINT", ""); s.api_key = g("AZURE_AI_FOUNDRY_API_KEY", "")
    s.api_version = g("AZURE_AI_FOUNDRY_API_VERSION", "2024-10-21")
    s.open_endpoint = g("AZURE_OPEN_MODEL_ENDPOINT", ""); s.open_api_key = g("AZURE_OPEN_MODEL_API_KEY", "")
    s.open_deployment = g("AZURE_OPEN_MODEL_DEPLOYMENT", "")
    s.frontier_deployment = g("AZURE_FRONTIER_MODEL_DEPLOYMENT", "")
    s.embedding_deployment = g("AZURE_EMBEDDING_DEPLOYMENT", "")
    def _p(env, key):
        v = g(env); 
        if v: p = Path(v); return p if p.is_absolute() else root / p
        return s.path(key)
    s.db_path = _p("SENTINEL_DB_PATH", "db"); s.chroma_path = _p("SENTINEL_CHROMA_PATH", "chroma")
    return s

_cached: Optional[Settings] = None
def get_settings(reload: bool = False) -> Settings:
    global _cached
    if _cached is None or reload: _cached = load_settings()
    return _cached

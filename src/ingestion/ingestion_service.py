"""Ingestion pipeline: adapt -> validate -> register assets -> write to SQLite (via repositories)."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Optional, Union
import pandas as pd
import yaml
from src.common.config import get_settings
from src.common.exceptions import DataIngestionError
from src.common.logging_config import get_logger
from src.ingestion.column_mapping import detect_columns, norm
from src.ingestion.normalization import to_long
from src.ingestion.validation import DataQualityReport, validate_long
from src.maintenance_app import repositories as R
from src.maintenance_app.database import transaction

log = get_logger("ingestion")
ASSET_ALIASES = {"asset_id": ["asset_id", "equipment_id", "machine_id", "id"], "asset_name": ["asset_name", "name", "equipment_name"],
                 "asset_type": ["asset_type", "type", "equipment_type"], "manufacturer": ["manufacturer", "vendor", "make"],
                 "location": ["location", "site", "area"], "criticality": ["criticality", "priority", "criticality_level"],
                 "installation_date": ["installation_date", "installed", "commissioned"], "operating_status": ["operating_status", "status"]}

def load_mapping(path_or_dict) -> Optional[dict]:
    if path_or_dict is None or isinstance(path_or_dict, dict): return path_or_dict
    p = Path(path_or_dict); txt = p.read_text(encoding="utf-8")
    return json.loads(txt) if p.suffix == ".json" else yaml.safe_load(txt)

def normalise_asset_meta(df: pd.DataFrame) -> pd.DataFrame:
    cols = {norm(c): c for c in df.columns}; out = pd.DataFrame()
    for k, aliases in ASSET_ALIASES.items():
        src = next((cols[a] for a in aliases if a in cols), None)
        if src is not None: out[k] = df[src].astype(str).str.strip()
    if "asset_id" not in out: raise DataIngestionError("asset metadata needs an asset id column")
    if "criticality" in out: out["criticality"] = out["criticality"].str.upper().where(out["criticality"].str.upper().isin(["LOW", "MEDIUM", "HIGH", "CRITICAL"]), "MEDIUM")
    return out

def register_assets(conn, meta: pd.DataFrame) -> list[str]:
    repo = R.AssetRepo(conn); new = []
    with transaction(conn):
        for r in meta.to_dict("records"):
            if not repo.exists(r["asset_id"]): new.append(r["asset_id"])
            r.setdefault("asset_name", r["asset_id"]); r.setdefault("asset_type", "unknown")
            existing = repo.get(r["asset_id"]) or {}
            repo.upsert({**existing, **{k: v for k, v in r.items() if v not in ("", "nan", None)}})
    return new

def ingest_dataframe(conn, df: pd.DataFrame, asset_meta: Optional[pd.DataFrame] = None, mapping: Optional[dict] = None,
                     source: str = "csv", unknown_assets: str = "register", dayfirst: bool = False, default_asset: Optional[str] = None) -> DataQualityReport:
    """unknown_assets: 'register' (create minimal asset, type 'unknown', criticality MEDIUM) | 'reject' (skip their rows)."""
    cfg = get_settings().sensor_mapping; rep = DataQualityReport(rows_in=len(df))
    cm = detect_columns(df, cfg, mapping)
    if not cm.ts_col or (not cm.asset_col and not default_asset):
        rep.errors.append(f"could not identify required columns (asset={cm.asset_col}, timestamp={cm.ts_col}); supply a mapping"); return rep
    if not cm.long_cols and not (cm.wide or cm.extras): rep.errors.append("no numeric sensor columns detected"); return rep
    long, st = to_long(df, cm, cfg, dayfirst, default_asset)
    rep.invalid_timestamps, rep.missing_values, rep.duplicates_removed = st["invalid_timestamps"], st["missing_values"], st["duplicates"]
    rep.warnings += st["warnings"] + ([f"non-numeric columns ignored: {cm.ignored}"] if cm.ignored else [])
    long = validate_long(long, rep)
    if rep.errors: return rep
    rep.assets_seen = sorted(long["asset_id"].unique())
    repo = R.AssetRepo(conn)
    if asset_meta is not None: rep.new_assets_registered += register_assets(conn, normalise_asset_meta(asset_meta))
    unknown = [a for a in rep.assets_seen if not repo.exists(a)]
    if unknown and unknown_assets == "register":
        rep.new_assets_registered += register_assets(conn, pd.DataFrame({"asset_id": unknown})); 
        rep.warnings.append(f"unknown assets registered with minimal metadata: {unknown}")
    elif unknown:
        rep.rejected_assets = unknown; long = long[~long["asset_id"].isin(unknown)]; rep.warnings.append(f"rows for unknown assets rejected: {unknown}")
    rep.rows_valid = len(long)
    rows = list(zip(long["asset_id"], long["timestamp"], long["sensor_name"], long["value"].astype(float), long["unit"], [source] * len(long)))
    with transaction(conn): rep.rows_inserted = R.SensorRepo(conn).bulk_insert(rows)
    rep.duplicates_already_in_db = rep.rows_valid - rep.rows_inserted
    log.info("ingested", extra={"ctx": rep.to_dict() | {"assets_seen": len(rep.assets_seen)}})
    return rep

def ingest_csv(conn, path: Union[str, Path], asset_meta_path: Optional[Union[str, Path]] = None, mapping=None, **kw) -> DataQualityReport:
    try: df = pd.read_csv(path)
    except Exception as e: raise DataIngestionError(f"cannot read CSV {path}: {e}") from e
    meta = pd.read_csv(asset_meta_path) if asset_meta_path else None
    return ingest_dataframe(conn, df, meta, load_mapping(mapping), source=Path(path).name, **kw)

def ingest_maintenance(conn, path) -> int:
    repo = R.MaintenanceRepo(conn); df = pd.read_csv(path).fillna("")
    with transaction(conn):
        for r in df.to_dict("records"): repo.add(r)
    return len(df)

def ingest_spares(conn, path) -> int:
    repo = R.SpareRepo(conn); df = pd.read_csv(path).fillna("")
    with transaction(conn):
        for r in df.to_dict("records"): repo.upsert(r)
    return len(df)

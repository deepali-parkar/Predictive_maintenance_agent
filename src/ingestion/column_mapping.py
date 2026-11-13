"""Column-name detection: asset id, timestamp, wide sensor columns, long-format columns, units, extra sensors."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Optional
import pandas as pd

def norm(name: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower())).strip("_")

def split_unit(col_norm: str, unit_tokens: dict) -> tuple[str, Optional[str]]:
    """'temperature_c' -> ('temperature','degC'); 'vibration_mm_s' -> ('vibration','mm/s')."""
    parts = col_norm.split("_")
    for n in (2, 1):
        if len(parts) > n and "_".join(parts[-n:]) in unit_tokens:
            return "_".join(parts[:-n]), unit_tokens["_".join(parts[-n:])]
    return col_norm, None

@dataclass
class ColumnMap:
    asset_col: Optional[str] = None
    ts_col: Optional[str] = None
    long_cols: Optional[tuple] = None                 # (sensor_col, value_col, unit_col|None)
    wide: dict = field(default_factory=dict)          # column -> (canonical sensor, unit|None)
    extras: dict = field(default_factory=dict)        # column -> (sensor name, unit|None)  (additional sensors)
    ignored: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

def _find(cols: dict, aliases: list) -> Optional[str]:
    for a in aliases:
        if a in cols: return cols[a]
    return None

def _is_numeric(s: pd.Series) -> bool:
    v = pd.to_numeric(s, errors="coerce"); nn = s.notna().sum()
    return nn > 0 and v.notna().sum() / nn > 0.5

def detect_columns(df: pd.DataFrame, cfg: dict, overrides: Optional[dict] = None) -> ColumnMap:
    ov = overrides or {}; cm = ColumnMap(); cols = {norm(c): c for c in df.columns}
    cm.asset_col = ov.get("asset_id") or _find(cols, cfg["asset_id_aliases"])
    cm.ts_col = ov.get("timestamp") or _find(cols, cfg["timestamp_aliases"])
    lf = cfg.get("long_format", {})
    sc, vc = _find(cols, lf.get("sensor_aliases", [])), _find(cols, lf.get("value_aliases", []))
    if ov.get("long") or (sc and vc and "sensors" not in ov):
        cm.long_cols = tuple(ov["long"]) if ov.get("long") else (sc, vc, _find(cols, lf.get("unit_aliases", [])))
        return cm
    unit_tokens = {k.lower(): v for k, v in cfg.get("unit_tokens", {}).items()}
    explicit = ov.get("sensors", {})
    for c in df.columns:
        if c in (cm.asset_col, cm.ts_col): continue
        if c in explicit:
            e = explicit[c]; cm.wide[c] = (e["sensor"], e.get("unit")); continue
        base, unit = split_unit(norm(c), unit_tokens); hit = None
        for sensor, sc_cfg in cfg["sensors"].items():
            if any(re.search(p, base) for p in sc_cfg["patterns"]): hit = sensor; break
        if not _is_numeric(df[c]):
            cm.ignored.append(c); continue
        if hit: cm.wide[c] = (hit, unit)
        else: cm.extras[c] = (base or norm(c), unit); cm.warnings.append(f"column '{c}' treated as additional sensor '{base}'")
    return cm

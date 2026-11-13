"""Timestamp parsing, unit conversion and conversion to the canonical long schema."""
from __future__ import annotations
from typing import Optional
import numpy as np, pandas as pd
from src.ingestion.column_mapping import ColumnMap, norm

def parse_timestamps(s: pd.Series, dayfirst: bool = False) -> pd.Series:
    """Returns naive-UTC datetimes; unparseable values become NaT (reported, never guessed)."""
    num = pd.to_numeric(s, errors="coerce")
    if num.notna().mean() > 0.9:                                  # epoch seconds / milliseconds
        unit = "ms" if num.dropna().abs().median() > 1e11 else "s"
        return pd.to_datetime(num, unit=unit, errors="coerce", utc=True).dt.tz_localize(None)
    return pd.to_datetime(s.astype(str).str.strip(), errors="coerce", utc=True, dayfirst=dayfirst, format="mixed").dt.tz_localize(None)

def convert(values: pd.Series, from_unit: Optional[str], to_unit: str, conv: dict) -> tuple[pd.Series, Optional[str]]:
    if not from_unit or from_unit == to_unit: return values, None
    c = conv.get(f"{from_unit}->{to_unit}")
    if c is None: return values, f"no conversion {from_unit}->{to_unit}; values left unconverted"
    return values * c["mul"] + c["add"], None

def to_long(df: pd.DataFrame, cm: ColumnMap, cfg: dict, dayfirst: bool = False, default_asset: Optional[str] = None
            ) -> tuple[pd.DataFrame, dict]:
    """Canonical output: asset_id, timestamp, sensor_name, value, unit. Returns (frame, stats)."""
    st = {"rows_in": len(df), "invalid_timestamps": 0, "missing_values": 0, "duplicates": 0, "warnings": list(cm.warnings)}
    conv = cfg.get("conversions", {}); canon = {k: v["canonical_unit"] for k, v in cfg["sensors"].items()}
    ts = parse_timestamps(df[cm.ts_col], dayfirst)
    aid = df[cm.asset_col].astype(str).str.strip() if cm.asset_col else pd.Series(default_asset, index=df.index)
    if not cm.asset_col and not default_asset: raise ValueError("no asset column found and no default_asset supplied")
    parts = []
    if cm.long_cols:
        sc, vc, uc = cm.long_cols
        sensors = df[sc].astype(str).map(lambda x: _canon_sensor(x, cfg)); vals = pd.to_numeric(df[vc], errors="coerce")
        units = df[uc].astype(str) if uc else pd.Series("", index=df.index)
        long = pd.DataFrame({"asset_id": aid, "timestamp": ts, "sensor_name": sensors, "value": vals, "unit": units})
        for s, g in long.groupby("sensor_name"):
            tgt = canon.get(s)
            if tgt:
                fu = g["unit"].mode().iloc[0] if g["unit"].str.len().gt(0).any() else None
                fu = {"c": "degC", "f": "degF"}.get(str(fu).lower(), fu) if fu else None
                v, w = convert(g["value"], fu, tgt, conv)
                long.loc[g.index, "value"] = v; long.loc[g.index, "unit"] = tgt if not w else g["unit"]
                if w: st["warnings"].append(f"{s}: {w}")
        parts.append(long)
    else:
        for col, (sensor, unit) in {**cm.wide, **cm.extras}.items():
            vals = pd.to_numeric(df[col], errors="coerce"); tgt = canon.get(sensor, unit or "")
            vals, w = convert(vals, unit, tgt, conv) if sensor in canon else (vals, None)
            if w: st["warnings"].append(f"{col}: {w}")
            parts.append(pd.DataFrame({"asset_id": aid, "timestamp": ts, "sensor_name": sensor, "value": vals, "unit": tgt}))
    out = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["asset_id", "timestamp", "sensor_name", "value", "unit"])
    st["invalid_timestamps"] = int(out["timestamp"].isna().sum() // max(1, len(parts))) if len(parts) else 0
    out = out[out["timestamp"].notna()]
    nan = out["value"].isna() | ~np.isfinite(out["value"].astype(float))
    st["missing_values"] = int(nan.sum()); out = out[~nan]                      # missing stays missing (never zero-filled)
    n0 = len(out); out = out.drop_duplicates(["asset_id", "timestamp", "sensor_name"], keep="last"); st["duplicates"] = n0 - len(out)
    out["timestamp"] = out["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
    return out.reset_index(drop=True), st

def _canon_sensor(name: str, cfg: dict) -> str:
    import re
    n = norm(name)
    for sensor, c in cfg["sensors"].items():
        if any(re.search(p, n) for p in c["patterns"]): return sensor
    return n

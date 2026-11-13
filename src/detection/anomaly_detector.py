"""Deterministic anomaly detection: z-score + deviation + absolute thresholds + persistence."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import numpy as np, pandas as pd
from src.detection.feature_calculator import baseline_stats, compute_features, pts_per_hour, to_series

@dataclass
class SensorDetection:
    sensor: str
    unit: str
    baseline_mean: float
    baseline_std: float
    features: pd.DataFrame
    flags: pd.Series                         # True where part of a SUSTAINED abnormal run
    windows: list = field(default_factory=list)   # [(start_ts, end_ts, hours)]
    spikes: list = field(default_factory=list)    # isolated single-point excursions (timestamps)
    thresholds: dict = field(default_factory=dict)

def thresholds_for(det_cfg: dict, asset_type: str, sensor: str) -> dict:
    return dict(det_cfg.get("thresholds", {}).get(asset_type, {}).get(sensor, {}))

def breach_level(v: float, th: dict) -> str:
    if v is None or np.isnan(v): return "NONE"
    if (th.get("crit_high") is not None and v >= th["crit_high"]) or (th.get("crit_low") is not None and v <= th["crit_low"]): return "CRITICAL"
    if (th.get("warn_high") is not None and v >= th["warn_high"]) or (th.get("warn_low") is not None and v <= th["warn_low"]): return "WARNING"
    return "NONE"

def _runs(mask: pd.Series) -> list[tuple[int, int]]:
    a = mask.to_numpy(dtype=bool); out = []; i = 0
    while i < len(a):
        if a[i]:
            j = i
            while j + 1 < len(a) and a[j + 1]: j += 1
            out.append((i, j)); i = j + 1
        else: i += 1
    return out

def detect_sensor(series: pd.Series, th: dict, cfg: dict, sensor: str = "", unit: str = "") -> Optional[SensorDetection]:
    bs = baseline_stats(series, cfg)
    if bs is None: return None
    bm, sd = bs; f = compute_features(series, bm, sd, cfg); pph = pts_per_hour(cfg["resample"])
    breach = f["roll_mean"].map(lambda v: breach_level(v, th))
    raw = ((f["z"].abs() >= cfg["z_threshold"]) & (f["dev_pct"].abs() >= cfg["min_deviation_pct"])) | (breach != "NONE")
    raw = raw.fillna(False); need = max(1, int(round(cfg["persistence_hours"] * pph)))
    flags = pd.Series(False, index=f.index); windows = []
    for i, j in _runs(raw):
        if j - i + 1 >= need:
            flags.iloc[i:j + 1] = True; windows.append((f.index[i], f.index[j], (j - i + 1) / pph))
    spikes = [t for t in f.index[(f["raw_z"].abs() >= cfg["spike_z_threshold"]) & ~flags]]
    return SensorDetection(sensor, unit, bm, sd, f, flags, windows, spikes, th)

def analyze_sensors(asset_type: str, readings: pd.DataFrame, det_cfg: dict, as_of: Optional[pd.Timestamp] = None) -> dict[str, SensorDetection]:
    """Run detection for every sensor in a long readings frame (timestamp, sensor_name, value, unit)."""
    cfg = det_cfg["analysis"]; out = {}
    for sensor, g in readings.groupby("sensor_name"):
        th = thresholds_for(det_cfg, asset_type, sensor); unit = th.get("unit") or (g["unit"].iloc[0] if "unit" in g and len(g) else "")
        d = detect_sensor(to_series(g, cfg["resample"], as_of), th, cfg, sensor, unit)
        if d is not None: out[sensor] = d
    return out

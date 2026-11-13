"""Rolling statistics: rolling mean / std, z-score vs asset baseline, trend slope. Pure pandas/numpy, no LLM."""
from __future__ import annotations
from typing import Optional
import numpy as np, pandas as pd

def pts_per_hour(freq: str) -> float:
    return pd.Timedelta("1h") / pd.Timedelta(freq)

def to_series(df_sensor: pd.DataFrame, freq: str = "1h", as_of: Optional[pd.Timestamp] = None) -> pd.Series:
    """Resample to a regular grid (mean). Gaps stay NaN - nothing is zero-filled."""
    s = df_sensor.set_index("timestamp")["value"].sort_index()
    if as_of is not None: s = s[s.index <= as_of]
    return s.resample(freq).mean() if len(s) else s

def baseline_stats(s: pd.Series, cfg: dict) -> Optional[tuple[float, float]]:
    """Baseline = first `baseline_hours` of the asset's own history (assumed healthy). None if too little data."""
    if s.dropna().empty: return None
    head = s[: s.index[0] + pd.Timedelta(hours=cfg["baseline_hours"])].dropna()
    if len(head) < cfg["min_baseline_points"]: return None
    mean = float(head.mean()); std = max(float(head.std(ddof=1)), 0.01 * abs(mean), 1e-9)
    return mean, std

def _slope(x: np.ndarray, ppd: float) -> float:
    m = ~np.isnan(x)
    if m.sum() < max(4, len(x) // 2): return np.nan
    t = np.arange(len(x))[m] / ppd
    return float(np.polyfit(t, x[m], 1)[0])

def compute_features(s: pd.Series, base_mean: float, base_std: float, cfg: dict) -> pd.DataFrame:
    pph = pts_per_hour(cfg["resample"]); n = max(3, int(round(cfg["smoothing_hours"] * pph)))
    roll = s.rolling(n, min_periods=max(3, n // 3))
    f = pd.DataFrame({"value": s, "roll_mean": roll.mean(), "roll_std": roll.std()})
    f["z"] = (f["roll_mean"] - base_mean) / base_std
    f["raw_z"] = (f["value"] - base_mean) / base_std
    f["dev_pct"] = (f["roll_mean"] - base_mean) / abs(base_mean) * 100.0
    sw = max(6, int(round(cfg["slope_window_hours"] * pph)))
    f["slope_per_day"] = f["roll_mean"].rolling(sw, min_periods=sw // 2).apply(lambda x: _slope(x, 24 * pph), raw=True)
    return f

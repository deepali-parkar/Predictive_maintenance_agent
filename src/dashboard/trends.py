"""Plotly time-series figure with thresholds, anomaly markers and flagged degradation windows."""
from __future__ import annotations
import plotly.graph_objects as go
from src.detection.anomaly_detector import SensorDetection

def trend_figure(sensor: str, det: SensorDetection, start, end, height: int = 330) -> go.Figure:
    f = det.features.loc[start:end]; fig = go.Figure(); unit = det.unit or ""
    fig.add_trace(go.Scatter(x=f.index, y=f["value"], mode="lines", name="reading", line=dict(width=1, color="#7f8c8d"), opacity=0.7))
    fig.add_trace(go.Scatter(x=f.index, y=f["roll_mean"], mode="lines", name="rolling mean", line=dict(width=2.2, color="#1f77b4")))
    fig.add_hrect(y0=det.baseline_mean - 3 * det.baseline_std, y1=det.baseline_mean + 3 * det.baseline_std, fillcolor="green", opacity=0.07, line_width=0)
    fig.add_hline(y=det.baseline_mean, line_dash="dot", line_color="green", opacity=0.6, annotation_text="baseline", annotation_position="bottom left")
    if len(f.dropna(subset=["value"])):
        lo, hi = f["value"].min(), f["value"].max()
        for key, label, color in (("warn_high", "warning", "orange"), ("crit_high", "critical", "red"), ("warn_low", "warning (low)", "orange"), ("crit_low", "critical (low)", "red")):
            v = det.thresholds.get(key)
            if v is not None and lo * 0.5 <= v <= hi * 1.8:
                fig.add_hline(y=v, line_dash="dash", line_color=color, annotation_text=f"{label} {v}", annotation_position="top left")
    flagged = f[det.flags.reindex(f.index).fillna(False)]
    if len(flagged): fig.add_trace(go.Scatter(x=flagged.index, y=flagged["value"], mode="markers", name="anomaly", marker=dict(color="red", size=5)))
    for ws, we, hrs in det.windows:
        if we >= f.index.min() and ws <= f.index.max():
            fig.add_vrect(x0=max(ws, f.index.min()).to_pydatetime(), x1=min(we, f.index.max()).to_pydatetime(), fillcolor="red", opacity=0.10, line_width=0)
    fig.update_layout(title=f"{sensor.title()} ({unit})", height=height, margin=dict(l=10, r=10, t=40, b=10), xaxis_title="Timestamp", yaxis_title=f"{sensor} [{unit}]",
                      legend=dict(orientation="h", y=-0.25))
    return fig

"""Detection evaluation vs ground-truth labels (point-level + event-level incl. lead time)."""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
from src.detection.anomaly_detector import analyze_sensors
from src.maintenance_app.services import get_services

def _prf(tp, fp, fn, tn) -> dict:
    p = tp / (tp + fp) if tp + fp else 0.0; r = tp / (tp + fn) if tp + fn else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": round(p, 4), "recall": round(r, 4), "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0,
            "false_positive_rate": round(fp / (fp + tn), 4) if fp + tn else 0.0, "false_negative_rate": round(fn / (fn + tp), 4) if fn + tp else 0.0}

def evaluate(conn, synthetic_dir: Path, det_cfg: dict, asset_ids: list[str]) -> dict:
    svc = get_services(conn); labels = pd.read_csv(Path(synthetic_dir) / "sensor_labels.csv", parse_dates=["timestamp"])
    events = pd.read_csv(Path(synthetic_dir) / "degradation_events.csv", parse_dates=["ramp_start", "label_onset", "end_time", "projected_failure_time"]).set_index("asset_id")
    persist = det_cfg["analysis"]["persistence_hours"]; rows = []; ev_out = []
    for aid in asset_ids:
        asset = svc.assets.get(aid); df = svc.sensors.history(aid)
        if asset is None or df.empty: continue
        dets = analyze_sensors(asset["asset_type"], df, det_cfg)
        lab = labels[labels.asset_id == aid]
        for sensor, d in dets.items():
            l = lab[lab.sensor_name == sensor].set_index("timestamp")["label"]; f = d.flags.reindex(l.index)
            ok = f.notna() & d.features["value"].reindex(l.index).notna(); l, f = l[ok], f[ok].astype(bool)
            rows.append({"asset_id": aid, "sensor": sensor, "tp": int(((l == 1) & f).sum()), "fp": int(((l == 0) & f).sum()), "fn": int(((l == 1) & ~f).sum()), "tn": int(((l == 0) & ~f).sum())})
        if aid in events.index:
            e = events.loc[aid]; ev_sensors = e["sensors"].split(";"); firsts = [w[0] for s in ev_sensors if s in dets for w in dets[s].windows if w[1] >= e["ramp_start"]]
            if firsts:
                t = min(firsts) + pd.Timedelta(hours=persist - 1)      # causal detection time: after persistence satisfied
                ev_out.append({"asset_id": aid, "detected": True, "detection_time": str(t), "delay_vs_label_onset_h": round((t - e["label_onset"]).total_seconds() / 3600, 1),
                               "lead_time_before_projected_failure_h": round((e["projected_failure_time"] - t).total_seconds() / 3600, 1)})
            else: ev_out.append({"asset_id": aid, "detected": False})
        else:
            fa = any(len(d.windows) for d in dets.values()); ev_out.append({"asset_id": aid, "detected": fa, "healthy_asset": True})
    t = pd.DataFrame(rows)
    tot = _prf(*[int(t[c].sum()) for c in ("tp", "fp", "fn", "tn")]) if len(t) else {}
    by_asset = {a: _prf(*[int(g[c].sum()) for c in ("tp", "fp", "fn", "tn")]) for a, g in t.groupby("asset_id")} if len(t) else {}
    by_sensor = {s: _prf(*[int(g[c].sum()) for c in ("tp", "fp", "fn", "tn")]) for s, g in t.groupby("sensor")} if len(t) else {}
    deg = [e for e in ev_out if not e.get("healthy_asset")]; healthy = [e for e in ev_out if e.get("healthy_asset")]
    leads = [e["lead_time_before_projected_failure_h"] for e in deg if e["detected"]]
    return {"assets": asset_ids, "point_level": tot, "by_asset": by_asset, "by_sensor": by_sensor, "events": ev_out,
            "event_level": {"degrading_assets": len(deg), "detected": sum(e["detected"] for e in deg), "event_recall": round(sum(e["detected"] for e in deg) / len(deg), 3) if deg else None,
                            "healthy_assets": len(healthy), "healthy_false_alarms": sum(e["detected"] for e in healthy),
                            "mean_lead_time_h": round(sum(leads) / len(leads), 1) if leads else None,
                            "mean_delay_vs_label_onset_h": round(sum(e["delay_vs_label_onset_h"] for e in deg if e["detected"]) / max(1, len(leads)), 1)}}

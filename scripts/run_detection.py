"""Run deterministic detection + risk engine over all assets in SQLite and persist risk events."""
import argparse, _bootstrap  # noqa
from src.maintenance_app.database import connect, init_db
from src.detection.detection_service import run_detection

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--asset", action="append"); ap.add_argument("--as-of"); a = ap.parse_args()
    c = connect(); init_db(c); res = run_detection(c, a.asset, a.as_of)
    print(f"{'asset':9} {'level':7} {'score':>6}  {'type':24} sensors")
    for r in sorted(res, key=lambda x: -x["risk_score"]):
        print(f"{r['asset_id']:9} {r['risk_level']:7} {r['risk_score']:6.1f}  {r['anomaly_type']:24} {','.join(r['affected_sensors'])}")

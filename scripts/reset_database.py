"""Restore / clean the operational DB.  Always backs up first.
  python scripts/reset_database.py --list
  python scripts/reset_database.py --remove-uploaded        # delete every asset that is not in the generated synthetic dataset
  python scripts/reset_database.py --remove PMP-101 NEW-1   # delete specific assets
  python scripts/reset_database.py --restore-synthetic      # rebuild the DB from scratch with the original synthetic dataset"""
import argparse, shutil, _bootstrap  # noqa
from datetime import datetime
import pandas as pd
from src.common.config import get_settings
from src.detection.detection_service import run_detection
from src.ingestion.dataset_adapter import ingest_csv, ingest_maintenance, ingest_spares
from src.maintenance_app.database import connect, init_db
from src.maintenance_app.services import get_services

def backup(db):
    if db.exists():
        dst = db.parent / "backups" / f"maintenance_{datetime.now():%Y%m%d_%H%M%S}.db"; dst.parent.mkdir(exist_ok=True); shutil.copy(db, dst); print("backup ->", dst)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--list", action="store_true"); ap.add_argument("--remove-uploaded", action="store_true")
    ap.add_argument("--remove", nargs="*"); ap.add_argument("--restore-synthetic", action="store_true"); a = ap.parse_args()
    s = get_settings(); sd = s.path("synthetic"); original = set(pd.read_csv(sd / "assets.csv").asset_id)
    if a.restore_synthetic:
        backup(s.db_path)
        for suf in ("", "-wal", "-shm"): (s.db_path.parent / (s.db_path.name + suf)).unlink(missing_ok=True)
        c = connect(); init_db(c); ingest_spares(c, sd / "spare_parts.csv"); print(ingest_csv(c, sd / "sensor_readings.csv", sd / "assets.csv").rows_inserted, "readings")
        ingest_maintenance(c, sd / "maintenance_history.csv"); print(len(run_detection(c)), "assets assessed")
    else:
        c = connect(); init_db(c); svc = get_services(c); ids = [x["asset_id"] for x in svc.assets.list()]
        if a.list or not (a.remove or a.remove_uploaded): print(f"{len(ids)} assets; original synthetic: {len(original)}; extra: {sorted(set(ids) - original)}")
        targets = (sorted(set(ids) - original) if a.remove_uploaded else []) + (a.remove or [])
        if targets: backup(s.db_path)
        for t in targets: print("deleted", t, svc.asset_admin.delete_asset(t, "SCRIPT:reset", force=True))
    c = connect(); print("assets now:", c.execute("SELECT COUNT(*) FROM assets").fetchone()[0])

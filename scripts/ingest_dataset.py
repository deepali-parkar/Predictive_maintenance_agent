"""Ingest CSV data into SQLite. Default: the generated synthetic dataset. Use --readings for any unseen dataset."""
import argparse, json, _bootstrap  # noqa
from src.common.config import get_settings
from src.ingestion.dataset_adapter import ingest_csv, ingest_maintenance, ingest_spares
from src.maintenance_app.database import connect, init_db

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--readings"); ap.add_argument("--assets"); ap.add_argument("--mapping", help="JSON/YAML column mapping override")
    ap.add_argument("--maintenance"); ap.add_argument("--spares"); ap.add_argument("--unknown-assets", default="register", choices=["register", "reject"])
    ap.add_argument("--dayfirst", action="store_true"); ap.add_argument("--default-asset")
    a = ap.parse_args(); s = get_settings(); d = s.path("synthetic"); conn = connect(); init_db(conn)
    if not a.readings:   # default synthetic dataset
        a.readings, a.assets = str(d / "sensor_readings.csv"), str(d / "assets.csv")
        a.maintenance, a.spares = a.maintenance or str(d / "maintenance_history.csv"), a.spares or str(d / "spare_parts.csv")
    if a.spares: print("spare parts:", ingest_spares(conn, a.spares))
    rep = ingest_csv(conn, a.readings, a.assets, a.mapping, unknown_assets=a.unknown_assets, dayfirst=a.dayfirst, default_asset=a.default_asset)
    if a.maintenance: print("maintenance records:", ingest_maintenance(conn, a.maintenance))
    print(json.dumps(rep.to_dict(), indent=2, default=str)); raise SystemExit(0 if rep.ok else 1)

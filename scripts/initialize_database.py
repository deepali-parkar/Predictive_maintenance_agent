"""Create / migrate data/maintenance.db."""
import argparse, _bootstrap  # noqa
from src.maintenance_app.database import connect, init_db, schema_version

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--db", default=None); a = ap.parse_args()
    c = connect(a.db); applied = init_db(c)
    print(f"Applied migrations: {applied or 'none (up to date)'} | schema version {schema_version(c)}")

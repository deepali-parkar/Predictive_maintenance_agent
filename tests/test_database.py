import sqlite3
from tests.helpers import make_env
from src.maintenance_app.database import connect, init_db, schema_version, transaction

def test_schema_tables_and_idempotent_migration():
    s, db = make_env(); c = connect(db)
    names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for t in ("assets", "sensor_readings", "risk_events", "maintenance_history", "work_orders", "spare_parts", "work_order_parts", "audit_log", "model_call_logs"): assert t in names
    assert init_db(c) == [] and schema_version(c) == 1

def test_transaction_rolls_back():
    s, db = make_env(); c = connect(db); n = c.execute("SELECT COUNT(*) FROM spare_parts").fetchone()[0]
    try:
        with transaction(c):
            c.execute("INSERT INTO spare_parts(part_id,part_name) VALUES('X','x')"); raise RuntimeError("boom")
    except RuntimeError: pass
    assert c.execute("SELECT COUNT(*) FROM spare_parts").fetchone()[0] == n

def test_single_db_populated_and_risk_events_persisted():
    s, db = make_env(); c = connect(db)
    assert c.execute("SELECT COUNT(*) FROM assets").fetchone()[0] == 20 and c.execute("SELECT COUNT(*) FROM sensor_readings").fetchone()[0] > 57000
    assert c.execute("SELECT COUNT(*) FROM risk_events WHERE status IN ('ACTIVE','NORMAL')").fetchone()[0] == 20

def test_work_order_status_check_constraint():
    s, db = make_env(); c = connect(db)
    try: c.execute("INSERT INTO work_orders VALUES('W','PMP-101',NULL,'t','p','HIGH','[]','BOGUS','a','t','t',NULL,NULL,NULL,'{}')"); assert False
    except sqlite3.IntegrityError: pass

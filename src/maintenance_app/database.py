"""Single operational SQLite database: connection factory, nested transactions, versioned migrations."""
from __future__ import annotations
import sqlite3, itertools
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union
from src.common.config import get_settings
from src.maintenance_app.migrations import MIGRATIONS

_sp = itertools.count(1)

def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

def connect(db_path: Optional[Union[str, Path]] = None) -> sqlite3.Connection:
    """Open a connection to THE operational database (all components share data/maintenance.db)."""
    path = Path(db_path) if db_path else get_settings().db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try: conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.DatabaseError: pass
    return conn

@contextmanager
def transaction(conn: sqlite3.Connection):
    """Atomic unit of work; nests via SAVEPOINT. Rolls back on any exception."""
    if conn.in_transaction:
        name = f"sp_{next(_sp)}"; conn.execute(f"SAVEPOINT {name}")
        try:
            yield conn; conn.execute(f"RELEASE {name}")
        except Exception:
            conn.execute(f"ROLLBACK TO {name}"); conn.execute(f"RELEASE {name}"); raise
    else:
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn; conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK"); raise

def init_db(conn: sqlite3.Connection) -> list[int]:
    """Create schema / apply pending migrations. Returns versions applied this call."""
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, name TEXT, applied_at TEXT)")
    done = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
    applied = []
    for version, name, sql in MIGRATIONS:
        if version in done: continue
        with transaction(conn):
            for stmt in [s.strip() for s in sql.split(";") if s.strip()]:
                conn.execute(stmt)
            conn.execute("INSERT INTO schema_migrations VALUES (?,?,?)", (version, name, now_iso()))
        applied.append(version)
    return applied

def schema_version(conn) -> int:
    r = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
    return r[0] or 0

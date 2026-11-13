"""Repository layer: ALL SQL lives here. Other layers never write SQL."""
from __future__ import annotations
import json, sqlite3, uuid
from typing import Any, Iterable, Optional
import pandas as pd
from src.maintenance_app.database import now_iso

def _d(row) -> Optional[dict]:
    return dict(row) if row is not None else None

class AssetRepo:
    def __init__(self, c: sqlite3.Connection): self.c = c
    def upsert(self, a: dict) -> None:
        ts = now_iso()
        self.c.execute("""INSERT INTO assets(asset_id,asset_name,asset_type,manufacturer,location,criticality,installation_date,operating_status,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(asset_id) DO UPDATE SET asset_name=excluded.asset_name, asset_type=excluded.asset_type,
            manufacturer=excluded.manufacturer, location=excluded.location, criticality=excluded.criticality,
            installation_date=excluded.installation_date, operating_status=excluded.operating_status, updated_at=excluded.updated_at""",
            (a["asset_id"], a["asset_name"], a["asset_type"], a.get("manufacturer"), a.get("location"), str(a.get("criticality", "MEDIUM")),
             a.get("installation_date"), a.get("operating_status", "RUNNING"), ts, ts))
    def get(self, asset_id: str) -> Optional[dict]:
        return _d(self.c.execute("SELECT * FROM assets WHERE asset_id=?", (asset_id,)).fetchone())
    def list(self) -> list[dict]:
        return [dict(r) for r in self.c.execute("SELECT * FROM assets ORDER BY asset_id")]
    def exists(self, asset_id: str) -> bool: return self.get(asset_id) is not None
    def counts(self, asset_id: str) -> dict:
        q = lambda sql: self.c.execute(sql, (asset_id,)).fetchone()[0]
        return {"readings": q("SELECT COUNT(*) FROM sensor_readings WHERE asset_id=?"), "risk_events": q("SELECT COUNT(*) FROM risk_events WHERE asset_id=?"),
                "work_orders": q("SELECT COUNT(*) FROM work_orders WHERE asset_id=?"), "approved_work_orders": q("SELECT COUNT(*) FROM work_orders WHERE asset_id=? AND status IN ('APPROVED','COMPLETED')"),
                "maintenance_records": q("SELECT COUNT(*) FROM maintenance_history WHERE asset_id=?")}
    def purge(self, asset_id: str) -> None:
        for sql in ("DELETE FROM work_order_parts WHERE work_order_id IN (SELECT work_order_id FROM work_orders WHERE asset_id=?)", "DELETE FROM work_orders WHERE asset_id=?",
                    "DELETE FROM risk_events WHERE asset_id=?", "DELETE FROM sensor_readings WHERE asset_id=?", "DELETE FROM maintenance_history WHERE asset_id=?", "DELETE FROM assets WHERE asset_id=?"):
            self.c.execute(sql, (asset_id,))

class SensorRepo:
    def __init__(self, c): self.c = c
    def bulk_insert(self, rows: Iterable[tuple]) -> int:
        """rows: (asset_id, timestamp, sensor_name, value, unit, data_source). Duplicates ignored."""
        before = self.c.total_changes
        self.c.executemany("INSERT OR IGNORE INTO sensor_readings(asset_id,timestamp,sensor_name,sensor_value,unit,data_source) VALUES(?,?,?,?,?,?)", list(rows))
        return self.c.total_changes - before
    def history(self, asset_id: str, sensor: Optional[str] = None, start: Optional[str] = None, end: Optional[str] = None,
                limit: Optional[int] = None) -> pd.DataFrame:
        q = "SELECT timestamp, sensor_name, sensor_value AS value, unit FROM sensor_readings WHERE asset_id=?"; p: list = [asset_id]
        if sensor: q += " AND sensor_name=?"; p.append(sensor)
        if start: q += " AND timestamp>=?"; p.append(start)
        if end: q += " AND timestamp<=?"; p.append(end)
        q += " ORDER BY timestamp"
        if limit: q += f" LIMIT {int(limit)}"
        df = pd.read_sql_query(q, self.c, params=p)
        if not df.empty: df["timestamp"] = pd.to_datetime(df["timestamp"])
        return df
    def sensors(self, asset_id: str) -> list[str]:
        return [r[0] for r in self.c.execute("SELECT DISTINCT sensor_name FROM sensor_readings WHERE asset_id=? ORDER BY 1", (asset_id,))]
    def time_range(self, asset_id: str) -> tuple[Optional[str], Optional[str]]:
        r = self.c.execute("SELECT MIN(timestamp), MAX(timestamp) FROM sensor_readings WHERE asset_id=?", (asset_id,)).fetchone()
        return r[0], r[1]
    def latest(self, asset_id: str) -> dict[str, dict]:
        out = {}
        for r in self.c.execute("""SELECT s.sensor_name, s.sensor_value, s.unit, s.timestamp FROM sensor_readings s
            JOIN (SELECT sensor_name, MAX(timestamp) mt FROM sensor_readings WHERE asset_id=? GROUP BY sensor_name) m
            ON s.sensor_name=m.sensor_name AND s.timestamp=m.mt WHERE s.asset_id=?""", (asset_id, asset_id)):
            out[r["sensor_name"]] = {"value": r["sensor_value"], "unit": r["unit"], "timestamp": r["timestamp"]}
        return out
    def count(self) -> int: return self.c.execute("SELECT COUNT(*) FROM sensor_readings").fetchone()[0]

class RiskRepo:
    def __init__(self, c): self.c = c
    @staticmethod
    def _row(r) -> dict:
        d = dict(r); d["affected_sensors"] = json.loads(d.get("affected_sensors") or "[]")
        d["evidence"] = json.loads(d.pop("evidence_json") or "{}"); d["confirmed_fault"] = bool(d["confirmed_fault"]); return d
    def insert(self, e: dict) -> str:
        rid = e.get("risk_event_id") or f"RE-{uuid.uuid4().hex[:10].upper()}"
        self.c.execute("""INSERT INTO risk_events(risk_event_id,asset_id,detected_at,window_start,window_end,risk_level,risk_score,anomaly_type,
            affected_sensors,evidence_json,confirmed_fault,status,detection_version) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (rid, e["asset_id"], e["detected_at"], e.get("window_start"), e.get("window_end"), e["risk_level"], e["risk_score"],
             e["anomaly_type"], json.dumps(e.get("affected_sensors", [])), json.dumps(e.get("evidence", {}), default=str),
             int(bool(e.get("confirmed_fault"))), e.get("status", "ACTIVE"), e.get("detection_version", "")))
        return rid
    def get(self, rid: str) -> Optional[dict]:
        r = self.c.execute("SELECT * FROM risk_events WHERE risk_event_id=?", (rid,)).fetchone(); return self._row(r) if r else None
    def list(self, asset_id: Optional[str] = None, status: Optional[str] = None, limit: int = 50) -> list[dict]:
        q, p = "SELECT * FROM risk_events WHERE 1=1", []
        if asset_id: q += " AND asset_id=?"; p.append(asset_id)
        if status: q += " AND status=?"; p.append(status)
        q += " ORDER BY detected_at DESC, rowid DESC LIMIT ?"; p.append(limit)
        return [self._row(r) for r in self.c.execute(q, p)]
    def current(self, asset_id: str) -> Optional[dict]:
        r = self.c.execute("SELECT * FROM risk_events WHERE asset_id=? AND status IN ('ACTIVE','NORMAL') ORDER BY detected_at DESC, rowid DESC LIMIT 1", (asset_id,)).fetchone()
        return self._row(r) if r else None
    def supersede(self, asset_id: str, keep_id: str) -> None:
        self.c.execute("UPDATE risk_events SET status='SUPERSEDED' WHERE asset_id=? AND risk_event_id<>? AND status IN ('ACTIVE','NORMAL')", (asset_id, keep_id))

class MaintenanceRepo:
    def __init__(self, c): self.c = c
    def add(self, m: dict) -> str:
        mid = m.get("maintenance_id") or f"MH-{uuid.uuid4().hex[:8].upper()}"
        self.c.execute("INSERT OR REPLACE INTO maintenance_history VALUES(?,?,?,?,?,?,?,?)",
                       (mid, m["asset_id"], m["maintenance_date"], m["maintenance_type"], m.get("description"), m.get("technician"),
                        m.get("parts_used"), m.get("outcome")))
        return mid
    def list(self, asset_id: str, limit: int = 50) -> list[dict]:
        return [dict(r) for r in self.c.execute("SELECT * FROM maintenance_history WHERE asset_id=? ORDER BY maintenance_date DESC LIMIT ?", (asset_id, limit))]
    def last_service_date(self, asset_id: str) -> Optional[str]:
        r = self.c.execute("SELECT MAX(maintenance_date) FROM maintenance_history WHERE asset_id=? AND maintenance_type<>'INSPECTION'", (asset_id,)).fetchone()
        return r[0]
    def last_date(self, asset_id: str) -> Optional[str]:
        return self.c.execute("SELECT MAX(maintenance_date) FROM maintenance_history WHERE asset_id=?", (asset_id,)).fetchone()[0]
    def confirmed_fault(self, asset_id: str) -> Optional[dict]:
        """A fault is 'confirmed' when the latest FAULT_CONFIRMED inspection post-dates the last non-inspection service."""
        r = self.c.execute("SELECT * FROM maintenance_history WHERE asset_id=? AND outcome='FAULT_CONFIRMED' ORDER BY maintenance_date DESC LIMIT 1", (asset_id,)).fetchone()
        if not r: return None
        ls = self.last_service_date(asset_id)
        return dict(r) if (ls is None or r["maintenance_date"] > ls) else None

class SpareRepo:
    def __init__(self, c): self.c = c
    def upsert(self, p: dict) -> None:
        self.c.execute("INSERT OR REPLACE INTO spare_parts VALUES(?,?,?,?,?,?,?)",
                       (p["part_id"], p["part_name"], p.get("compatible_asset_types", ""), int(p.get("quantity_available", 0)),
                        int(p.get("reorder_level", 0)), p.get("unit_cost"), p.get("description", "")))
    def get(self, pid: str) -> Optional[dict]: return _d(self.c.execute("SELECT * FROM spare_parts WHERE part_id=?", (pid,)).fetchone())
    def list(self) -> list[dict]: return [dict(r) for r in self.c.execute("SELECT * FROM spare_parts ORDER BY part_id")]
    def compatible(self, asset_type: str) -> list[dict]:
        out = []
        for p in self.list():
            types = [t.strip().lower() for t in (p["compatible_asset_types"] or "").replace(";", ",").split(",") if t.strip()]
            if asset_type.lower() in types or "all" in types: out.append(p)
        return out

class WorkOrderRepo:
    def __init__(self, c): self.c = c
    def next_id(self) -> str:
        day = now_iso()[:10].replace("-", "")
        n = self.c.execute("SELECT COUNT(*) FROM work_orders WHERE work_order_id LIKE ?", (f"WO-{day}-%",)).fetchone()[0] + 1
        return f"WO-{day}-{n:04d}"
    def insert(self, w: dict) -> None:
        self.c.execute("""INSERT INTO work_orders(work_order_id,asset_id,risk_event_id,title,problem_description,priority,recommended_steps,status,
            created_by,created_at,updated_at,evidence_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (w["work_order_id"], w["asset_id"], w.get("risk_event_id"), w["title"], w["problem_description"], w["priority"],
             json.dumps(w.get("recommended_steps", [])), w["status"], w["created_by"], w["created_at"], w["created_at"],
             json.dumps(w.get("evidence", {}), default=str)))
    @staticmethod
    def _row(r) -> dict:
        d = dict(r); d["recommended_steps"] = json.loads(d.get("recommended_steps") or "[]")
        d["evidence"] = json.loads(d.pop("evidence_json") or "{}"); return d
    def get(self, wid: str) -> Optional[dict]:
        r = self.c.execute("SELECT * FROM work_orders WHERE work_order_id=?", (wid,)).fetchone(); return self._row(r) if r else None
    def list(self, asset_id: Optional[str] = None, status: Optional[str] = None) -> list[dict]:
        q, p = "SELECT * FROM work_orders WHERE 1=1", []
        if asset_id: q += " AND asset_id=?"; p.append(asset_id)
        if status: q += " AND status=?"; p.append(status)
        return [self._row(r) for r in self.c.execute(q + " ORDER BY created_at DESC, rowid DESC", p)]
    def update(self, wid: str, fields: dict) -> None:
        if "recommended_steps" in fields: fields = {**fields, "recommended_steps": json.dumps(fields["recommended_steps"])}
        if "evidence" in fields: fields = {**fields, "evidence_json": json.dumps(fields.pop("evidence"), default=str)}
        fields["updated_at"] = now_iso()
        cols = ", ".join(f"{k}=?" for k in fields)
        self.c.execute(f"UPDATE work_orders SET {cols} WHERE work_order_id=?", [*fields.values(), wid])
    def set_parts(self, wid: str, parts: list[dict]) -> None:
        self.c.execute("DELETE FROM work_order_parts WHERE work_order_id=?", (wid,))
        for p in parts:
            self.c.execute("INSERT INTO work_order_parts VALUES(?,?,?,?)", (wid, p["part_id"], int(p.get("quantity", 1)), p.get("notes", "")))
    def parts(self, wid: str) -> list[dict]:
        return [dict(r) for r in self.c.execute("""SELECT wp.part_id, sp.part_name, wp.quantity, wp.notes, sp.quantity_available
            FROM work_order_parts wp JOIN spare_parts sp USING(part_id) WHERE wp.work_order_id=?""", (wid,))]

class AuditRepo:
    def __init__(self, c): self.c = c
    def add(self, actor, action, entity_type, entity_id, before=None, after=None, reason="", correlation_id="") -> None:
        self.c.execute("INSERT INTO audit_log(timestamp,actor,action,entity_type,entity_id,before_json,after_json,reason,correlation_id) VALUES(?,?,?,?,?,?,?,?,?)",
                       (now_iso(), actor, action, entity_type, entity_id, json.dumps(before, default=str) if before is not None else None,
                        json.dumps(after, default=str) if after is not None else None, reason, correlation_id))
    def list(self, entity_id: Optional[str] = None, entity_type: Optional[str] = None, limit: int = 200) -> list[dict]:
        q, p = "SELECT * FROM audit_log WHERE 1=1", []
        if entity_id: q += " AND entity_id=?"; p.append(entity_id)
        if entity_type: q += " AND entity_type=?"; p.append(entity_type)
        return [dict(r) for r in self.c.execute(q + " ORDER BY audit_id DESC LIMIT ?", [*p, limit])]

class ModelLogRepo:
    def __init__(self, c): self.c = c
    def add(self, l: dict) -> None:
        self.c.execute("""INSERT INTO model_call_logs(timestamp,asset_id,risk_event_id,risk_level,model_name,model_type,routing_reason,prompt_tokens,
            completion_tokens,total_tokens,estimated_cost,operation,success,error_message,execution_seconds,correlation_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (now_iso(), l.get("asset_id"), l.get("risk_event_id"), l.get("risk_level"), l.get("model_name"), l.get("model_type"),
             l.get("routing_reason"), l.get("prompt_tokens"), l.get("completion_tokens"), l.get("total_tokens"), l.get("estimated_cost"),
             l.get("operation"), int(bool(l.get("success", True))), l.get("error_message", ""), l.get("execution_seconds"), l.get("correlation_id", "")))
    def list(self, limit: int = 1000) -> pd.DataFrame:
        return pd.read_sql_query("SELECT * FROM model_call_logs ORDER BY model_call_id DESC LIMIT ?", self.c, params=[limit])

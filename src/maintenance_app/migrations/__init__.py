"""Ordered, idempotent schema migrations. Add new (version, name, sql) tuples to evolve the schema."""
MIGRATIONS = [
(1, "initial_schema", """
CREATE TABLE assets (
  asset_id TEXT PRIMARY KEY, asset_name TEXT NOT NULL, asset_type TEXT NOT NULL, manufacturer TEXT, location TEXT,
  criticality TEXT NOT NULL DEFAULT 'MEDIUM', installation_date TEXT, operating_status TEXT NOT NULL DEFAULT 'RUNNING',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE sensor_readings (
  reading_id INTEGER PRIMARY KEY AUTOINCREMENT, asset_id TEXT NOT NULL REFERENCES assets(asset_id),
  timestamp TEXT NOT NULL, sensor_name TEXT NOT NULL, sensor_value REAL NOT NULL, unit TEXT DEFAULT '',
  data_source TEXT DEFAULT 'csv');
CREATE INDEX idx_sr_asset ON sensor_readings(asset_id);
CREATE INDEX idx_sr_ts ON sensor_readings(timestamp);
CREATE INDEX idx_sr_sensor ON sensor_readings(sensor_name);
CREATE UNIQUE INDEX uq_sr ON sensor_readings(asset_id, timestamp, sensor_name);
CREATE TABLE risk_events (
  risk_event_id TEXT PRIMARY KEY, asset_id TEXT NOT NULL REFERENCES assets(asset_id), detected_at TEXT NOT NULL,
  window_start TEXT, window_end TEXT, risk_level TEXT NOT NULL, risk_score REAL NOT NULL, anomaly_type TEXT NOT NULL,
  affected_sensors TEXT, evidence_json TEXT, confirmed_fault INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'ACTIVE', detection_version TEXT);
CREATE INDEX idx_re_asset ON risk_events(asset_id);
CREATE TABLE maintenance_history (
  maintenance_id TEXT PRIMARY KEY, asset_id TEXT NOT NULL REFERENCES assets(asset_id), maintenance_date TEXT NOT NULL,
  maintenance_type TEXT NOT NULL, description TEXT, technician TEXT, parts_used TEXT, outcome TEXT);
CREATE INDEX idx_mh_asset ON maintenance_history(asset_id);
CREATE TABLE spare_parts (
  part_id TEXT PRIMARY KEY, part_name TEXT NOT NULL, compatible_asset_types TEXT, quantity_available INTEGER NOT NULL DEFAULT 0,
  reorder_level INTEGER NOT NULL DEFAULT 0, unit_cost REAL, description TEXT);
CREATE TABLE work_orders (
  work_order_id TEXT PRIMARY KEY, asset_id TEXT NOT NULL REFERENCES assets(asset_id), risk_event_id TEXT REFERENCES risk_events(risk_event_id),
  title TEXT NOT NULL, problem_description TEXT NOT NULL, priority TEXT NOT NULL, recommended_steps TEXT,
  status TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','APPROVED','REJECTED','COMPLETED')),
  created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, approved_by TEXT, approved_at TEXT,
  rejection_reason TEXT, evidence_json TEXT);
CREATE INDEX idx_wo_asset ON work_orders(asset_id);
CREATE TABLE work_order_parts (
  work_order_id TEXT NOT NULL REFERENCES work_orders(work_order_id), part_id TEXT NOT NULL REFERENCES spare_parts(part_id),
  quantity INTEGER NOT NULL DEFAULT 1, notes TEXT, PRIMARY KEY (work_order_id, part_id));
CREATE TABLE audit_log (
  audit_id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL,
  entity_type TEXT NOT NULL, entity_id TEXT NOT NULL, before_json TEXT, after_json TEXT, reason TEXT, correlation_id TEXT);
CREATE INDEX idx_audit_entity ON audit_log(entity_type, entity_id);
CREATE TABLE model_call_logs (
  model_call_id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL, asset_id TEXT, risk_event_id TEXT, risk_level TEXT,
  model_name TEXT, model_type TEXT, routing_reason TEXT, prompt_tokens INTEGER, completion_tokens INTEGER, total_tokens INTEGER,
  estimated_cost REAL, operation TEXT, success INTEGER NOT NULL DEFAULT 1, error_message TEXT, execution_seconds REAL,
  correlation_id TEXT);
"""),
]

# ARCHITECTURE & module contracts (finalised)
Layering (dependencies point downward): `dashboard / scripts / mcp_server` → `agent` → `rag, detection, ingestion, review` → `maintenance_app (services → repositories → database)` → SQLite. `common/contracts.py` is shared by all.

| Concern | Module | Contract |
|---|---|---|
| Canonical readings | ingestion | `asset_id, timestamp, sensor_name, value, unit` → `sensor_readings` |
| Detection | detection.anomaly_detector | `SensorDetection` (features, flags, windows) |
| Evidence | detection.evidence_builder | `DetectionEvidence` |
| Risk | detection.risk_engine | `RiskAssessment` → `risk_events.evidence_json` |
| Operational access | mcp_server.tools | 7 tools, JSON in/out, roles in `permissions.py` |
| Knowledge | rag | `RetrievedEvidence` with `citation_ref` |
| LLM outputs | contracts | `MaintenanceExplanation`, `MaintenanceRecommendation`, `WorkOrderDraftContent` |
| Draft | contracts | `WorkOrderDraft` / `WorkOrderRequest` / `WorkOrderResponse` |
| Routing & cost | agent.model_router | `ModelRoutingDecision`, `ModelCallLog` → `model_call_logs` |
| Governance | maintenance_app.services.WorkOrderService | agent: create DRAFT only; planner: edit/approve/reject; every change → `audit_log` |

Rules: agent touches operational data only via MCP (model-call logging goes through `ModelLogService`); detection/risk never call an LLM; router never alters risk; LLM never supplies identifiers (asset/risk-event ids injected from verified state).

"""Centralised Pydantic contracts shared by dataset, SQLite, detection, MCP, RAG, LangGraph and dashboard."""
from __future__ import annotations
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field
from src.common.enums import (AnomalyType, Criticality, Decision, ModelType, Priority, RiskLevel,
                              WorkOrderStatus)

class Asset(BaseModel):
    asset_id: str
    asset_name: str
    asset_type: str
    manufacturer: Optional[str] = None
    location: Optional[str] = None
    criticality: Criticality = Criticality.MEDIUM
    installation_date: Optional[str] = None
    operating_status: str = "RUNNING"

class SensorReading(BaseModel):
    asset_id: str
    timestamp: str
    sensor_name: str
    value: float
    unit: str = ""
    data_source: str = "csv"

class DetectionEvidence(BaseModel):
    asset_id: str
    sensor_name: str
    unit: str = ""
    detected_at: str
    window_start: str
    window_end: str
    baseline_mean: float
    baseline_std: float
    current_mean: float
    z_score: float
    trend_slope_per_day: float
    trend_slope_pct_per_day: float
    deviation_pct: float
    direction: str                      # up | down
    threshold_warning: Optional[float] = None
    threshold_critical: Optional[float] = None
    threshold_breach: str = "NONE"      # NONE | WARNING | CRITICAL
    detection_rule: str = ""
    anomaly_type: AnomalyType = AnomalyType.NONE
    sustained_hours: float = 0.0
    severity: float = Field(0.0, ge=0.0, le=1.0)

class RiskAssessment(BaseModel):
    asset_id: str
    risk_level: RiskLevel
    risk_score: float = Field(0.0, ge=0.0, le=100.0)
    risk_reason: str
    anomaly_type: AnomalyType = AnomalyType.NONE
    evidence: list[DetectionEvidence] = Field(default_factory=list)
    affected_sensors: list[str] = Field(default_factory=list)
    trend_summary: str = ""
    signal_confidence: float = Field(0.0, ge=0.0, le=1.0)
    confirmed_fault: bool = False
    predicted_risk: str = ""            # human-readable classification (not a confirmed fault)
    monitoring_urgency: str = ""
    breakdown: dict = Field(default_factory=dict)
    window_start: Optional[str] = None
    window_end: Optional[str] = None

class RiskEvent(BaseModel):
    risk_event_id: str
    asset_id: str
    detected_at: str
    window_start: Optional[str] = None
    window_end: Optional[str] = None
    risk_level: RiskLevel
    risk_score: float
    anomaly_type: AnomalyType
    affected_sensors: list[str] = Field(default_factory=list)
    evidence: dict = Field(default_factory=dict)
    confirmed_fault: bool = False
    status: str = "ACTIVE"
    detection_version: str = ""

class RetrievedEvidence(BaseModel):
    source_id: str                       # chunk id
    citation_ref: str                    # e.g. [DOC:MAN-PUMP-BEARING#2]
    document_id: str
    document_title: str
    document_type: str
    section: str = ""
    text: str
    asset_type: str = ""
    failure_mode: str = ""
    page_number: Optional[int] = None
    source_file: str = ""
    similarity_score: float = 0.0

class ManualEvidence(BaseModel):
    citation_ref: str
    summary: str

class MaintenanceExplanation(BaseModel):
    likely_failure_mode: str = "UNDETERMINED"
    failure_mode_confidence: float = Field(0.0, ge=0.0, le=1.0)
    risk_explanation: str
    supporting_sensor_evidence: list[str] = Field(default_factory=list)
    supporting_manual_evidence: list[ManualEvidence] = Field(default_factory=list)
    supporting_maintenance_evidence: list[str] = Field(default_factory=list)
    uncertainty: str = ""
    recommended_inspections: list[str] = Field(default_factory=list)
    evidence_sufficient: bool = True
    confirmed_fault_acknowledged: bool = False

class MaintenanceRecommendation(BaseModel):
    decision: Decision
    rationale: str
    urgency: str = ""
    monitoring_advice: str = ""
    confirmed_fault_acknowledged: bool = False
    guardrail_note: str = ""

class PartRequest(BaseModel):
    part_id: str
    quantity: int = Field(1, ge=1)
    notes: str = ""

class WorkOrderDraftContent(BaseModel):
    """What the LLM writes (no identifiers - those are injected by the agent from verified state)."""
    title: str
    problem_description: str
    priority: Priority
    recommended_steps: list[str] = Field(default_factory=list)
    required_parts: list[PartRequest] = Field(default_factory=list)
    evidence_references: list[str] = Field(default_factory=list)
    rationale: str = ""

class WorkOrderDraft(WorkOrderDraftContent):
    asset_id: str
    risk_event_id: Optional[str] = None

class WorkOrderRequest(WorkOrderDraft):
    correlation_id: str = ""
    requested_by: str = "AGENT:sentinel"

class WorkOrderResponse(BaseModel):
    work_order_id: Optional[str] = None
    status: str = ""
    created_at: str = ""
    validation_result: dict = Field(default_factory=dict)

class ModelRoutingDecision(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    model_type: ModelType
    deployment: str = ""
    risk_level: RiskLevel
    routing_reason: str
    escalated: bool = False
    signals: list[str] = Field(default_factory=list)

class ModelCallLog(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    asset_id: Optional[str] = None
    risk_event_id: Optional[str] = None
    risk_level: Optional[str] = None
    model_name: str = ""
    model_type: str = ""
    routing_reason: str = ""
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    estimated_cost: Optional[float] = None   # None == unavailable (never invented)
    operation: str = ""
    success: bool = True
    error_message: str = ""
    execution_seconds: Optional[float] = None
    correlation_id: str = ""

"""Shared enumerations."""
from enum import Enum

class RiskLevel(str, Enum):
    LOW = "LOW"; MEDIUM = "MEDIUM"; HIGH = "HIGH"

class Criticality(str, Enum):
    LOW = "LOW"; MEDIUM = "MEDIUM"; HIGH = "HIGH"; CRITICAL = "CRITICAL"

class WorkOrderStatus(str, Enum):
    DRAFT = "DRAFT"; APPROVED = "APPROVED"; REJECTED = "REJECTED"; COMPLETED = "COMPLETED"

class Priority(str, Enum):
    LOW = "LOW"; MEDIUM = "MEDIUM"; HIGH = "HIGH"; URGENT = "URGENT"

class Decision(str, Enum):
    CREATE_DRAFT = "CREATE_DRAFT"; MONITOR = "MONITOR"
    INSPECT_FIRST = "INSPECT_FIRST"; INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

class ModelType(str, Enum):
    OPEN = "open"; FRONTIER = "frontier"

class AnomalyType(str, Enum):
    NONE = "NONE"; ISOLATED_ANOMALY = "ISOLATED_ANOMALY"
    PERSISTENT_ABNORMALITY = "PERSISTENT_ABNORMALITY"
    PREDICTED_DEGRADATION = "PREDICTED_DEGRADATION"; CONFIRMED_FAULT = "CONFIRMED_FAULT"

class RiskStatus(str, Enum):
    NORMAL = "NORMAL"; ACTIVE = "ACTIVE"; SUPERSEDED = "SUPERSEDED"

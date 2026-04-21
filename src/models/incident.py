"""Data models for incident response."""

from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field
from datetime import datetime


class SeverityLevel(str, Enum):
    """Severity levels for incidents."""
    P1 = "P1"  # Critical - service down
    P2 = "P2"  # High - significant degradation
    P3 = "P3"  # Medium - minor issues
    P4 = "P4"  # Low - informational


class IncidentStatus(str, Enum):
    """Status of incident."""
    INVESTIGATING = "investigating"
    ROOT_CAUSE_IDENTIFIED = "root_cause_identified"
    RESOLVED = "resolved"
    ESCALATED = "escalated"


class Alert(BaseModel):
    """Incoming alert from monitoring system."""
    alert_id: str = Field(..., description="Unique alert ID")
    service: str = Field(..., description="Affected service name")
    alert_type: str = Field(..., description="Type of alert (e.g., high_error_rate)")
    severity: SeverityLevel = Field(..., description="Alert severity")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    description: str = Field(..., description="Alert description")
    metric_value: Optional[float] = Field(None, description="Current metric value")
    threshold: Optional[float] = Field(None, description="Threshold that was breached")
    affected_region: Optional[str] = Field(None, description="Geographic region affected")
    tags: Dict[str, str] = Field(default_factory=dict, description="Additional tags")


class LogEntry(BaseModel):
    """Log entry from upstream service."""
    timestamp: datetime
    level: str  # ERROR, WARN, INFO
    service: str
    message: str
    stack_trace: Optional[str] = None
    context: Dict[str, Any] = Field(default_factory=dict)


class IncidentContext(BaseModel):
    """Context gathered during incident investigation."""
    alert: Alert
    severity: SeverityLevel
    status: IncidentStatus = Field(default=IncidentStatus.INVESTIGATING)
    recent_logs: List[LogEntry] = Field(default_factory=list)
    metric_data: Dict[str, Any] = Field(default_factory=dict)
    root_cause: Optional[str] = None
    root_cause_confidence: Optional[float] = None  # 0.0 to 1.0
    suggested_remediation: Optional[str] = None
    remediation_steps: List[str] = Field(default_factory=list)
    evidence: List[str] = Field(default_factory=list)
    investigation_timeline: List[Dict[str, Any]] = Field(default_factory=list)


class IncidentSummary(BaseModel):
    """Final incident summary for communication."""
    incident_id: str
    service: str
    severity: SeverityLevel
    status: IncidentStatus
    duration_minutes: float
    root_cause: str
    root_cause_confidence: float
    remediation_applied: Optional[str] = None
    escalated: bool = False
    escalation_reason: Optional[str] = None
    investigation_notes: str
    next_steps: List[str]
    slack_channel_link: Optional[str] = None
    jira_ticket_url: Optional[str] = None

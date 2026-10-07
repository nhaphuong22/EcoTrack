"""
Pydantic Schemas for Anomaly Detection & Incident Lifecycle Management
Supports state transitions: OPEN -> ACKNOWLEDGED -> RESOLVED
"""

from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


VALID_ANOMALY_STATUS = Literal["OPEN", "ACKNOWLEDGED", "RESOLVED"]


class AnomalyEvent(BaseModel):
    """Telemetry anomaly event returned to Frontend dashboard."""
    id: str
    timestamp: str
    subsystem: str = Field(default="Chiller & HVAC Plant", description="Affected facility subsystem")
    severity: str = Field(..., description="Severity classification (LOW, MEDIUM, CRITICAL)")
    anomaly_score: float = Field(..., description="Isolation Forest anomaly decision score")
    actual_kwh: float = Field(..., description="Actual recorded power consumption in kWh")
    predicted_kwh: float = Field(..., description="Baseline expected power consumption in kWh")
    delta_kwh: float = Field(..., description="Excess residual power consumption above baseline")
    outdoor_temp_c: float = Field(..., description="Outside air temperature in Celsius")
    estimated_waste_vnd: float = Field(..., description="Calculated energy waste cost in VND")
    estimated_waste_usd: float = Field(..., description="Calculated energy waste cost in USD")
    status: str = Field(default="OPEN", description="Current incident lifecycle state: OPEN, ACKNOWLEDGED, RESOLVED")
    description: Optional[str] = Field(default=None, description="Diagnostic explanation or reason")
    suggested_action: Optional[str] = Field(default=None, description="Recommended operational corrective action")

    model_config = ConfigDict(from_attributes=True)


class AnomalyStatusUpdateRequest(BaseModel):
    """Payload for updating an anomaly event's lifecycle status."""
    status: VALID_ANOMALY_STATUS = Field(
        ...,
        description="Target lifecycle state. Must be one of: OPEN, ACKNOWLEDGED, RESOLVED",
        examples=["ACKNOWLEDGED"],
    )
    note: Optional[str] = Field(
        default=None,
        description="Optional operator remediation note or diagnostic log",
        examples=["Technician inspected HVAC chiller C-1. Setpoint recalibrated."],
    )


class AnomalyStatusUpdateResponse(BaseModel):
    """Response payload confirming anomaly status transition."""
    id: str
    previous_status: str
    current_status: str
    updated_at: datetime
    note: Optional[str] = None
    message: str

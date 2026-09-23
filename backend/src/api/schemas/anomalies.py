from pydantic import BaseModel
from typing import Optional

class AnomalyEvent(BaseModel):
    id: str
    timestamp: str
    subsystem: str
    severity: str
    anomaly_score: float
    actual_kwh: float
    predicted_kwh: float
    delta_kwh: float
    outdoor_temp_c: float
    estimated_waste_vnd: float
    estimated_waste_usd: float
    status: str = "New"
    description: Optional[str] = None

from pydantic import BaseModel
from typing import List, Optional

class TimeSeriesPoint(BaseModel):
    timestamp: str
    meter_reading_kwh: float
    predicted_kwh: Optional[float] = None
    lower_bound_95: Optional[float] = None
    upper_bound_95: Optional[float] = None
    outdoor_temperature_c: float
    relative_humidity_pct: float
    is_anomaly: bool = False
    anomaly_score: float = 0.0
    severity: str = "Normal"
    anomaly_reason: Optional[str] = None

class TimeSeriesResponse(BaseModel):
    building_id: str
    count: int
    data: List[TimeSeriesPoint]

class MetricSummaryResponse(BaseModel):
    building_id: str
    total_consumption_kwh: float
    peak_demand_kw: float
    predicted_baseline_kwh: float
    total_anomalies_detected: int
    estimated_waste_cost_vnd: float
    estimated_waste_cost_usd: float

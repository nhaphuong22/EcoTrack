import asyncio
from typing import Any, Dict, List, Optional
from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.data_pipeline.serving_frame import get_anomaly_events, score_live_readings

router = APIRouter(prefix="/internal/anomalies", tags=["Anomaly Detection"])


class LiveScoreItem(BaseModel):
    building_id: str = "office_tower_01"
    zone_id: Optional[str] = None
    meter_id: Optional[str] = None
    timestamp: str
    meter_reading_kwh: float
    interval_seconds: Optional[float] = 3600.0
    outdoor_temperature_c: Optional[float] = None
    recent_meter_hourly_kwhs: List[float] = Field(default_factory=list)
    recent_building_hourly_kwhs: List[float] = Field(default_factory=list)


class LiveScoreRequest(BaseModel):
    items: List[LiveScoreItem] = Field(..., max_length=200)


def _detect_anomalies_pure() -> List[Dict[str, Any]]:
    return get_anomaly_events()


@router.get("/detect")
@router.post("/detect")
async def detect_anomalies():
    """Pure ML Anomaly detection calculation."""
    return await asyncio.to_thread(_detect_anomalies_pure)


@router.post("/score")
async def score_anomalies(req: LiveScoreRequest):
    """Score live ingested meter readings with XGBoost baseline + Isolation Forest."""
    items = [item.model_dump() for item in req.items]
    return await asyncio.to_thread(score_live_readings, items)

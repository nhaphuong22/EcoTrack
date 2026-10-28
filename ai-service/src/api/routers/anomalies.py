import asyncio
from typing import Any, Dict, List
from fastapi import APIRouter

from src.data_pipeline.serving_frame import get_anomaly_events

router = APIRouter(prefix="/internal/anomalies", tags=["Anomaly Detection"])


def _detect_anomalies_pure() -> List[Dict[str, Any]]:
    return get_anomaly_events()


@router.get("/detect")
@router.post("/detect")
async def detect_anomalies():
    """Pure ML Anomaly detection calculation."""
    return await asyncio.to_thread(_detect_anomalies_pure)

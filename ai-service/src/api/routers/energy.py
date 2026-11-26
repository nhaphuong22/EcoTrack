import asyncio
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from src.data_pipeline.serving_frame import (
    compute_energy_metrics,
    get_serving_frame,
    score_timeseries_from_series,
)

router = APIRouter(prefix="/internal/energy", tags=["Energy Telemetry"])


class SeriesPoint(BaseModel):
    timestamp: str
    meter_reading_kwh: float
    outdoor_temperature_c: Optional[float] = None


class TimeseriesRequest(BaseModel):
    building_id: str = "office_tower_01"
    recent_readings: List[SeriesPoint] = Field(..., min_length=25, max_length=720)


def _compute_energy_metrics() -> Dict[str, Any]:
    frame = get_serving_frame()
    metrics = compute_energy_metrics(frame)
    return {
        "building_id": metrics["building_id"],
        "total_consumption_kwh": metrics["total_consumption_kwh"],
        "peak_demand_kw": metrics["peak_demand_kw"],
        "predicted_baseline_kwh": metrics["predicted_baseline_kwh"],
        "total_anomalies_detected": metrics["total_anomalies_detected"],
        "estimated_waste_cost_vnd": metrics["estimated_waste_cost_vnd"],
        "estimated_waste_cost_usd": metrics["estimated_waste_cost_usd"],
    }


def _serialize_timeseries(df_slice, building_id: str = "office_tower_01") -> Dict[str, Any]:
    points = [
        {
            "timestamp": str(row["timestamp"]),
            "meter_reading_kwh": float(row["meter_reading_kwh"]),
            "predicted_kwh": float(row["predicted_kwh"]),
            "lower_bound_95": float(row["lower_bound_95"]),
            "upper_bound_95": float(row["upper_bound_95"]),
            "outdoor_temperature_c": float(row["outdoor_temperature_c"]),
            "relative_humidity_pct": None,
            "is_anomaly": bool(row["is_anomaly"]),
            "anomaly_score": float(row["anomaly_score"]),
            "severity": str(row["severity"]),
            "anomaly_reason": None,
        }
        for _, row in df_slice.iterrows()
    ]
    return {
        "building_id": building_id,
        "count": len(points),
        "data": points,
    }


def _get_timeseries(limit: int) -> Dict[str, Any]:
    frame = get_serving_frame()
    return _serialize_timeseries(frame.tail(limit))


@router.get("/metrics")
async def get_energy_metrics():
    """Computes aggregated energy metrics for building."""
    return await asyncio.to_thread(_compute_energy_metrics)


@router.get("/timeseries")
async def get_timeseries(limit: int = Query(default=24, ge=1, le=720)):
    """Fetches real-time telemetry slice with predictions and anomaly flags."""
    return await asyncio.to_thread(_get_timeseries, limit)


@router.post("/timeseries")
async def post_timeseries(req: TimeseriesRequest, limit: int = Query(default=168, ge=1, le=720)):
    """Scores live hourly DB readings through XGBoost and Isolation Forest."""
    rows = [point.model_dump() for point in req.recent_readings]
    return await asyncio.to_thread(
        lambda: _serialize_timeseries(score_timeseries_from_series(rows, limit=limit), req.building_id)
    )

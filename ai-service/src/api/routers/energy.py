import asyncio
from typing import Any, Dict
from fastapi import APIRouter, Query

from src.data_pipeline.serving_frame import compute_energy_metrics, get_serving_frame

router = APIRouter(prefix="/internal/energy", tags=["Energy Telemetry"])


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


def _get_timeseries(limit: int) -> Dict[str, Any]:
    frame = get_serving_frame()
    df_slice = frame.tail(limit)
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
        "building_id": "office_tower_01",
        "count": len(points),
        "data": points,
    }


@router.get("/metrics")
async def get_energy_metrics():
    """Computes aggregated energy metrics for building."""
    return await asyncio.to_thread(_compute_energy_metrics)


@router.get("/timeseries")
async def get_timeseries(limit: int = Query(default=24, ge=1, le=720)):
    """Fetches real-time telemetry slice with predictions and anomaly flags."""
    return await asyncio.to_thread(_get_timeseries, limit)

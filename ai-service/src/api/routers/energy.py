import asyncio
from typing import Any, Dict, List
from fastapi import APIRouter, Query

from src.data_pipeline.bdg2_loader import data_loader
from src.models.forecaster_xgboost import energy_forecaster
from src.models.anomaly_isolation_forest import anomaly_detector

router = APIRouter(prefix="/internal/energy", tags=["Energy Telemetry"])


def _compute_energy_metrics() -> Dict[str, Any]:
    df = data_loader.get_or_create_data()
    df_fc = energy_forecaster.predict_horizon(df)
    df_anom = anomaly_detector.detect_anomalies(df_fc)

    total_kwh = float(df_anom["meter_reading_kwh"].sum())
    peak_kw = float(df_anom["meter_reading_kwh"].max())
    baseline_kwh = float(df_anom["predicted_kwh"].sum())
    anom_count = int(df_anom["is_anomaly"].sum())

    waste_kwh = float(df_anom[df_anom["is_anomaly"]]["residual"].clip(lower=0).sum())
    waste_vnd = waste_kwh * 3100
    waste_usd = waste_kwh * 0.125

    return {
        "building_id": "office_tower_01",
        "total_consumption_kwh": round(total_kwh, 1),
        "peak_demand_kw": round(peak_kw, 1),
        "predicted_baseline_kwh": round(baseline_kwh, 1),
        "total_anomalies_detected": anom_count,
        "estimated_waste_cost_vnd": round(waste_vnd, 0),
        "estimated_waste_cost_usd": round(waste_usd, 2),
    }


def _get_timeseries(limit: int) -> Dict[str, Any]:
    df = data_loader.get_or_create_data()
    df_fc = energy_forecaster.predict_horizon(df)
    df_anom = anomaly_detector.detect_anomalies(df_fc)

    df_slice = df_anom.tail(limit)
    points = []
    for _, row in df_slice.iterrows():
        points.append({
            "timestamp": str(row["timestamp"]),
            "meter_reading_kwh": float(row["meter_reading_kwh"]),
            "predicted_kwh": float(row["predicted_kwh"]),
            "lower_bound_95": float(row["lower_bound_95"]),
            "upper_bound_95": float(row["upper_bound_95"]),
            "outdoor_temperature_c": float(row["outdoor_temperature_c"]),
            "relative_humidity_pct": float(row.get("relative_humidity_pct", 65.0)),
            "is_anomaly": bool(row["is_anomaly"]),
            "anomaly_score": float(row["anomaly_score"]),
            "severity": str(row["severity"]),
            "anomaly_reason": row.get("anomaly_reason") if bool(row["is_anomaly"]) else None,
        })
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

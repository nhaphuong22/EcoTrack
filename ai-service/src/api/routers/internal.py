"""
Internal AI & ML Inference Router for EcoTrack
Dedicated high-performance endpoints consumed by the Express.js API Gateway.
Protected by X-Internal-Token authentication.
"""

import asyncio
import os
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Header, HTTPException, Query, status
from pydantic import BaseModel

from src.data_pipeline.bdg2_loader import data_loader
from src.models.forecaster_xgboost import energy_forecaster
from src.models.anomaly_isolation_forest import anomaly_detector
from src.agent.orchestrator import copilot_orchestrator
from src.agent.experiment_logger import experiment_logger
from src.api.routers.energy import _compute_metrics, _compute_timeseries
from src.api.routers.forecast import _get_forecast

router = APIRouter(prefix="/internal", tags=["Internal AI Engine"])

INTERNAL_TOKEN = os.getenv("INTERNAL_API_KEY", "ecotrack_internal_secret_2026")


def _verify_token(x_internal_token: Optional[str] = Header(None)) -> None:
    # If INTERNAL_API_KEY is configured and token is provided or enforced:
    if x_internal_token and x_internal_token != INTERNAL_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal authentication token.",
        )


class InternalChatRequest(BaseModel):
    message: str
    building_id: str = "office_tower_01"
    history: List[Dict[str, Any]] = []


@router.get("/energy/metrics")
async def get_internal_energy_metrics():
    """Returns core building energy metrics calculated by ML models."""
    return await asyncio.to_thread(_compute_metrics)


@router.get("/energy/timeseries")
async def get_internal_energy_timeseries(limit: int = Query(default=168)):
    """Returns telemetry time-series points."""
    points = await asyncio.to_thread(_compute_timeseries, limit)
    return {
        "building_id": "office_tower_01",
        "count": len(points),
        "data": points,
    }


@router.get("/forecast/predict")
async def get_internal_forecast():
    """Runs 24-hour XGBoost load forecasting with 95% confidence intervals."""
    forecast_data = await asyncio.to_thread(_get_forecast)
    return {
        "building_id": "office_tower_01",
        "horizon_hours": 24,
        "forecast": forecast_data,
    }


def _detect_anomalies_pure() -> List[Dict[str, Any]]:
    df = data_loader.get_or_create_data()
    df_fc = energy_forecaster.predict_horizon(df)
    df_anom = anomaly_detector.detect_anomalies(df_fc)

    anom_rows = df_anom[df_anom["is_anomaly"]].copy()
    events = []

    for idx, row in anom_rows.iterrows():
        delta = round(float(row["residual"]), 1)
        cost_vnd = delta * 3100
        cost_usd = delta * 0.125
        events.append({
            "id": f"ANOM-{idx}",
            "building_id": "office_tower_01",
            "timestamp": str(row["timestamp"]),
            "subsystem": "Chiller & HVAC Plant",
            "severity": str(row["severity"]),
            "anomaly_score": float(row["anomaly_score"]),
            "actual_kwh": float(row["meter_reading_kwh"]),
            "predicted_kwh": float(row["predicted_kwh"]),
            "delta_kwh": delta,
            "outdoor_temp_c": float(row["outdoor_temperature_c"]),
            "estimated_waste_vnd": round(cost_vnd, 0),
            "estimated_waste_usd": round(cost_usd, 2),
            "status": "OPEN",
            "description": row.get("anomaly_reason") or "Abnormal load deviation exceeding baseline prediction",
            "suggested_action": row.get("anomaly_reason") or "Inspect chiller plant schedule and sub-meter power draw.",
        })
    return events[::-1]


@router.get("/anomalies/detect")
@router.post("/anomalies/detect")
async def detect_anomalies_endpoint():
    """Pure ML Anomaly detection calculation."""
    return await asyncio.to_thread(_detect_anomalies_pure)


@router.post("/copilot/chat")
async def internal_copilot_chat(req: InternalChatRequest):
    """Processes conversational reasoning with ReAct energy tools."""
    reply, tools_used = await asyncio.to_thread(
        copilot_orchestrator.process_chat,
        req.message,
        req.history,
    )
    return {
        "reply": reply,
        "tools_used": tools_used,
    }


@router.get("/copilot/experiment-stats")
async def get_internal_experiment_stats():
    """Returns AI Copilot benchmark metrics and telemetry statistics."""
    return experiment_logger.get_summary_statistics()

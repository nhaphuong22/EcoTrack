import asyncio
from typing import Any, Dict, List, Optional
from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.data_pipeline.serving_frame import predict_next_24h, predict_next_24h_from_series

router = APIRouter(prefix="/internal/forecast", tags=["AI Forecasting"])


class SeriesPoint(BaseModel):
    timestamp: str
    meter_reading_kwh: float
    outdoor_temperature_c: Optional[float] = None


class ForecastSeriesRequest(BaseModel):
    building_id: str = "office_tower_01"
    recent_readings: List[SeriesPoint] = Field(..., min_length=24, max_length=720)


def _serialize_forecast(forecast_df) -> List[Dict[str, Any]]:
    return [
        {
            "timestamp": str(row["timestamp"]),
            "predicted_kwh": float(row["predicted_kwh"]),
            "lower_bound_95": float(row["lower_bound_95"]),
            "upper_bound_95": float(row["upper_bound_95"]),
            "outdoor_temperature_c": float(row["outdoor_temperature_c"]),
        }
        for _, row in forecast_df.iterrows()
    ]


def _get_forecast() -> List[Dict[str, Any]]:
    return _serialize_forecast(predict_next_24h())


@router.get("/predict")
async def get_forecast():
    """Runs 24-hour XGBoost load forecasting with 95% confidence intervals."""
    forecast_data = await asyncio.to_thread(_get_forecast)
    return {
        "building_id": "office_tower_01",
        "horizon_hours": 24,
        "forecast": forecast_data,
    }


@router.post("/predict")
async def predict_forecast_from_series(req: ForecastSeriesRequest):
    """Runs 24-hour XGBoost forecasting directly from live PostgreSQL hourly readings."""
    rows = [point.model_dump() for point in req.recent_readings]
    forecast_data = await asyncio.to_thread(lambda: _serialize_forecast(predict_next_24h_from_series(rows)))
    return {
        "building_id": req.building_id,
        "horizon_hours": 24,
        "source": "live_db",
        "forecast": forecast_data,
    }

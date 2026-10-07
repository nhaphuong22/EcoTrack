import asyncio
from typing import Any, Dict, List
from fastapi import APIRouter

from src.data_pipeline.bdg2_loader import data_loader
from src.models.forecaster_xgboost import energy_forecaster

router = APIRouter(prefix="/internal/forecast", tags=["AI Forecasting"])


def _get_forecast() -> List[Dict[str, Any]]:
    df = data_loader.get_or_create_data()
    df_fc = energy_forecaster.predict_horizon(df)
    last_24h = df_fc.tail(24)

    results = []
    for _, row in last_24h.iterrows():
        results.append({
            "timestamp": str(row["timestamp"]),
            "predicted_kwh": float(row["predicted_kwh"]),
            "lower_bound_95": float(row["lower_bound_95"]),
            "upper_bound_95": float(row["upper_bound_95"]),
            "outdoor_temperature_c": float(row["outdoor_temperature_c"]),
        })
    return results


@router.get("/predict")
async def get_forecast():
    """Runs 24-hour XGBoost load forecasting with 95% confidence intervals."""
    forecast_data = await asyncio.to_thread(_get_forecast)
    return {
        "building_id": "office_tower_01",
        "horizon_hours": 24,
        "forecast": forecast_data,
    }

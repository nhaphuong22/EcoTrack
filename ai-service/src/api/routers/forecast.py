import asyncio
from fastapi import APIRouter
from src.data_pipeline.bdg2_loader import data_loader
from src.models.forecaster_xgboost import energy_forecaster

router = APIRouter(prefix="/api/v1/forecast", tags=["Forecasting Engine"])

def _get_forecast():
    df = data_loader.get_or_create_data()
    df_fc = energy_forecaster.predict_horizon(df)
    last_24h = df_fc.tail(24)
    
    results = []
    for _, row in last_24h.iterrows():
        results.append({
            "timestamp": row["timestamp"],
            "predicted_kwh": float(row["predicted_kwh"]),
            "lower_bound_95": float(row["lower_bound_95"]),
            "upper_bound_95": float(row["upper_bound_95"]),
            "outdoor_temperature_c": float(row["outdoor_temperature_c"])
        })
    return results

@router.get("/predict")
async def get_forecast():
    # AD-2: Non-blocking computation
    forecast_data = await asyncio.to_thread(_get_forecast)
    return {
        "building_id": "office_tower_01",
        "horizon_hours": 24,
        "forecast": forecast_data
    }

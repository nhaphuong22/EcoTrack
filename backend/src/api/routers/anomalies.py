import asyncio
from fastapi import APIRouter
from typing import List
from src.api.schemas.anomalies import AnomalyEvent
from src.data_pipeline.bdg2_loader import data_loader
from src.models.forecaster_xgboost import energy_forecaster
from src.models.anomaly_isolation_forest import anomaly_detector

router = APIRouter(prefix="/api/v1/anomalies", tags=["Anomaly Detection"])

def _get_anomalies_list():
    df = data_loader.get_or_create_data()
    df_fc = energy_forecaster.predict_horizon(df)
    df_anom = anomaly_detector.detect_anomalies(df_fc)
    
    anom_rows = df_anom[df_anom["is_anomaly"]].copy()
    events = []
    
    for idx, row in anom_rows.iterrows():
        delta = round(float(row["residual"]), 1)
        cost_vnd = delta * 3100
        cost_usd = delta * 0.125
        
        events.append(AnomalyEvent(
            id=f"ANOM-{idx}",
            timestamp=row["timestamp"],
            subsystem="Chiller & HVAC Plant",
            severity=str(row["severity"]),
            anomaly_score=float(row["anomaly_score"]),
            actual_kwh=float(row["meter_reading_kwh"]),
            predicted_kwh=float(row["predicted_kwh"]),
            delta_kwh=delta,
            outdoor_temp_c=float(row["outdoor_temperature_c"]),
            estimated_waste_vnd=round(cost_vnd, 0),
            estimated_waste_usd=round(cost_usd, 2),
            status="New",
            description=row.get("anomaly_reason") or "Abnormal load deviation exceeding baseline prediction"
        ))
    return events[::-1] # Reverse to have newest first

@router.get("/events", response_model=List[AnomalyEvent])
async def list_anomalies():
    # AD-2: Non-blocking computation
    events = await asyncio.to_thread(_get_anomalies_list)
    return events

import asyncio
from typing import Any, Dict, List
from fastapi import APIRouter

from src.data_pipeline.bdg2_loader import data_loader
from src.models.forecaster_xgboost import energy_forecaster
from src.models.anomaly_isolation_forest import anomaly_detector

router = APIRouter(prefix="/internal/anomalies", tags=["Anomaly Detection"])


def _detect_anomalies_pure() -> List[Dict[str, Any]]:
    df = data_loader.get_or_create_data()
    df_fc = energy_forecaster.predict_horizon(df)
    df_anom = anomaly_detector.detect_anomalies(df_fc)

    anom_rows = df_anom[df_anom["is_anomaly"]].copy()
    events = []

    for idx, row in anom_rows.iterrows():
        delta = max(0.0, float(row["meter_reading_kwh"]) - float(row["predicted_kwh"]))
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


@router.get("/detect")
@router.post("/detect")
async def detect_anomalies():
    """Pure ML Anomaly detection calculation."""
    return await asyncio.to_thread(_detect_anomalies_pure)

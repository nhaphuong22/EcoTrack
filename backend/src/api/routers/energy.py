import asyncio
from fastapi import APIRouter, Query
from src.api.schemas.energy import TimeSeriesResponse, TimeSeriesPoint, MetricSummaryResponse
from src.data_pipeline.bdg2_loader import data_loader
from src.models.forecaster_xgboost import energy_forecaster
from src.models.anomaly_isolation_forest import anomaly_detector

router = APIRouter(prefix="/api/v1/energy", tags=["Energy Telemetry"])

def _compute_timeseries(limit: int):
    df = data_loader.get_or_create_data()
    df_fc = energy_forecaster.predict_horizon(df)
    df_anom = anomaly_detector.detect_anomalies(df_fc)
    
    if limit > 0:
        df_sliced = df_anom.tail(limit)
    else:
        df_sliced = df_anom
        
    points = []
    for _, row in df_sliced.iterrows():
        points.append(TimeSeriesPoint(
            timestamp=row["timestamp"],
            meter_reading_kwh=float(row["meter_reading_kwh"]),
            predicted_kwh=float(row["predicted_kwh"]),
            lower_bound_95=float(row["lower_bound_95"]),
            upper_bound_95=float(row["upper_bound_95"]),
            outdoor_temperature_c=float(row["outdoor_temperature_c"]),
            relative_humidity_pct=float(row["relative_humidity_pct"]),
            is_anomaly=bool(row["is_anomaly"]),
            anomaly_score=float(row["anomaly_score"]),
            severity=str(row["severity"]),
            anomaly_reason=row.get("anomaly_reason")
        ))
    return points

def _compute_metrics():
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
    
    return MetricSummaryResponse(
        building_id="office_tower_01",
        total_consumption_kwh=round(total_kwh, 1),
        peak_demand_kw=round(peak_kw, 1),
        predicted_baseline_kwh=round(baseline_kwh, 1),
        total_anomalies_detected=anom_count,
        estimated_waste_cost_vnd=round(waste_vnd, 0),
        estimated_waste_cost_usd=round(waste_usd, 2)
    )

@router.get("/timeseries", response_model=TimeSeriesResponse)
async def get_timeseries(limit: int = Query(default=168, description="Number of past hourly points (default: 168 = 7 days)")):
    # AD-2: Non-blocking ML computation via asyncio.to_thread
    points = await asyncio.to_thread(_compute_timeseries, limit)
    return TimeSeriesResponse(
        building_id="office_tower_01",
        count=len(points),
        data=points
    )

@router.get("/metrics", response_model=MetricSummaryResponse)
async def get_metrics():
    # AD-2: Non-blocking computation
    metrics = await asyncio.to_thread(_compute_metrics)
    return metrics

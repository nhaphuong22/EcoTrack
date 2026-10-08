from typing import Any, Dict, List

from src.config import get_tariff_rate_usd, get_tariff_rate_vnd
from src.data_pipeline.bdg2_loader import data_loader
from src.data_pipeline.serving_frame import compute_energy_metrics, get_serving_frame
from src.models.anomaly_isolation_forest import anomaly_detector
from src.models.forecaster_xgboost import energy_forecaster


def query_metrics() -> Dict[str, Any]:
    """Truy vấn các chỉ số điện năng tổng quan của tòa nhà."""
    frame = get_serving_frame()
    metrics = compute_energy_metrics(frame)
    return {
        "building_id": metrics["building_id"],
        "total_consumption_kwh": metrics["total_consumption_kwh"],
        "peak_demand_kw": metrics["peak_demand_kw"],
        "baseline_kwh": metrics["predicted_baseline_kwh"],
        "anomalies_detected": metrics["total_anomalies_detected"],
        "estimated_waste_kwh": metrics["estimated_waste_kwh"],
        "estimated_waste_vnd": metrics["estimated_waste_cost_vnd"],
        "estimated_waste_usd": metrics["estimated_waste_cost_usd"],
    }


def get_anomalies(limit: int = 5) -> List[Dict[str, Any]]:
    """Truy vấn danh sách các điểm và sự kiện bất thường gần nhất."""
    df = data_loader.get_or_create_data()
    df_fc = energy_forecaster.predict_horizon(df)
    df_anom = anomaly_detector.detect_anomalies(df_fc)

    anom_rows = df_anom[df_anom["is_anomaly"]].tail(limit)
    events = []

    for idx, row in anom_rows.iterrows():
        events.append({
            "id": f"ANOM-{idx}",
            "timestamp": row["timestamp"],
            "severity": row["severity"],
            "anomaly_score": float(row["anomaly_score"]),
            "actual_kwh": float(row["meter_reading_kwh"]),
            "predicted_kwh": float(row["predicted_kwh"]),
            "delta_kwh": round(float(row["residual"]), 1),
            "outdoor_temp_c": float(row["outdoor_temperature_c"]),
            "reason": row["anomaly_reason"] or "Độ lệch phụ tải bất thường không giải thích bằng nhiệt độ"
        })
    return events

def query_forecast_summary() -> Dict[str, Any]:
    """Truy vấn thông tin tóm tắt dự báo phụ tải điện 24 giờ tới."""
    df = data_loader.get_or_create_data()
    df_fc = energy_forecaster.predict_horizon(df)
    last_24h = df_fc.tail(24)

    max_row = last_24h.loc[last_24h["predicted_kwh"].idxmax()]
    return {
        "forecast_horizon": "24 hours",
        "expected_peak_kw": float(max_row["predicted_kwh"]),
        "peak_timestamp": max_row["timestamp"],
        "average_forecast_kwh": round(float(last_24h["predicted_kwh"].mean()), 1),
        "confidence_interval_95": "±16.7 kW"
    }


def calculate_waste_cost(delta_kwh: float, duration_hours: float = 1.0) -> Dict[str, Any]:
    """Tính toán chi phí lãng phí điện năng dựa trên kWh chênh lệch."""
    total_waste_kwh = delta_kwh * duration_hours
    vnd = total_waste_kwh * get_tariff_rate_vnd()
    usd = total_waste_kwh * get_tariff_rate_usd()
    return {
        "excess_kwh": round(total_waste_kwh, 1),
        "cost_vnd": round(vnd, 0),
        "cost_usd": round(usd, 2),
    }

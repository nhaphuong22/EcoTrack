from typing import Any, Dict, List

from src.config import get_tariff_rate_usd, get_tariff_rate_vnd
from src.data_pipeline.serving_frame import (
    compute_energy_metrics,
    get_anomaly_events,
    get_serving_frame,
    predict_next_24h,
)


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
    events = get_anomaly_events()
    if limit and limit > 0:
        return events[:limit]
    return events


def query_forecast_summary() -> Dict[str, Any]:
    """Truy vấn thông tin tóm tắt dự báo phụ tải điện 24 giờ tới."""
    df_fc = predict_next_24h()
    max_idx = df_fc["predicted_kwh"].idxmax()
    max_row = df_fc.loc[max_idx]
    ci = float(max_row["upper_bound_95"] - max_row["predicted_kwh"])
    return {
        "forecast_horizon": "24 hours",
        "expected_peak_kw": float(max_row["predicted_kwh"]),
        "peak_timestamp": str(max_row["timestamp"]),
        "average_forecast_kwh": round(float(df_fc["predicted_kwh"].mean()), 1),
        "confidence_interval_95": f"±{ci:.1f} kW",
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

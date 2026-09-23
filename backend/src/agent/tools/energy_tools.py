from typing import Dict, Any, List
from src.data_pipeline.bdg2_loader import data_loader
from src.models.forecaster_xgboost import energy_forecaster
from src.models.anomaly_isolation_forest import anomaly_detector

def query_metrics() -> Dict[str, Any]:
    """Truy vấn các chỉ số điện năng tổng quan của tòa nhà."""
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
        "baseline_kwh": round(baseline_kwh, 1),
        "anomalies_detected": anom_count,
        "estimated_waste_kwh": round(waste_kwh, 1),
        "estimated_waste_vnd": round(waste_vnd, 0),
        "estimated_waste_usd": round(waste_usd, 2)
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
    vnd = total_waste_kwh * 3100
    usd = total_waste_kwh * 0.125
    return {
        "excess_kwh": round(total_waste_kwh, 1),
        "cost_vnd": round(vnd, 0),
        "cost_usd": round(usd, 2)
    }

"""
Unit tests for EcoTrack Anomaly Detection on the unified pipeline:
- Validates serving-frame -> anomaly event mapping and key contracts
- Validates delta_kwh = max(0, actual - predicted) and tariff-based waste calculations
- Validates newest-first event ordering and metrics agreement
- Validates Copilot tools get_anomalies and query_forecast_summary on the unified pipeline
"""
import pandas as pd
import pytest

from src.agent.tools.energy_tools import get_anomalies, query_forecast_summary
from src.config import get_tariff_rate_usd, get_tariff_rate_vnd
from src.data_pipeline.serving_frame import (
    compute_energy_metrics,
    get_anomaly_events,
    get_serving_frame,
    predict_next_24h,
)


def test_get_anomaly_events_real_frame():
    """Verify anomaly events generated from the real serving frame."""
    frame = get_serving_frame()
    events = get_anomaly_events()
    anom_rows = frame[frame["is_anomaly"]]

    assert len(events) == len(anom_rows)
    metrics = compute_energy_metrics(frame)
    assert len(events) == metrics["total_anomalies_detected"]

    # Newest first ordering: matches reversed chronological order of frame
    expected_timestamps = anom_rows["timestamp"].tolist()[::-1]
    assert [e["timestamp"] for e in events] == expected_timestamps

    expected_keys = {
        "id", "building_id", "timestamp", "subsystem", "severity",
        "anomaly_score", "actual_kwh", "predicted_kwh", "delta_kwh",
        "outdoor_temp_c", "estimated_waste_vnd", "estimated_waste_usd",
        "status", "description", "suggested_action"
    }

    tariff_vnd = get_tariff_rate_vnd()
    tariff_usd = get_tariff_rate_usd()

    for event in events:
        assert expected_keys.issubset(set(event.keys()))
        assert event["building_id"] == "office_tower_01"
        assert event["timestamp"].endswith("Z")
        assert event["severity"] in ["Normal", "Medium", "Critical"]
        assert event["status"] == "OPEN"
        assert event["delta_kwh"] >= 0.0
        assert event["delta_kwh"] == max(0.0, event["actual_kwh"] - event["predicted_kwh"])
        assert event["estimated_waste_vnd"] == round(event["delta_kwh"] * tariff_vnd, 0)
        assert event["estimated_waste_usd"] == round(event["delta_kwh"] * tariff_usd, 2)


def test_get_anomaly_events_mock_edge_cases():
    """Verify negative residual clamping and non-anomaly filtering with mock frame."""
    mock_frame = pd.DataFrame({
        "timestamp": ["2026-01-01T01:00:00Z", "2026-01-01T02:00:00Z", "2026-01-01T03:00:00Z"],
        "meter_reading_kwh": [100.0, 50.0, 300.0],
        "predicted_kwh": [80.0, 80.0, 100.0],
        "residual": [20.0, -30.0, 200.0],
        "outdoor_temperature_c": [25.0, 26.0, 27.0],
        "anomaly_score": [0.85, 0.90, 0.10],
        "is_anomaly": [True, True, False],
        "severity": ["Medium", "Medium", "Normal"],
    })

    events = get_anomaly_events(mock_frame)
    # Only 2 anomalous rows, newest first (02:00:00Z then 01:00:00Z)
    assert len(events) == 2
    assert events[0]["timestamp"] == "2026-01-01T02:00:00Z"
    assert events[1]["timestamp"] == "2026-01-01T01:00:00Z"

    # Negative delta clamped to 0.0
    neg_event = events[0]
    assert neg_event["actual_kwh"] == 50.0
    assert neg_event["predicted_kwh"] == 80.0
    assert neg_event["delta_kwh"] == 0.0
    assert neg_event["estimated_waste_vnd"] == 0.0
    assert neg_event["estimated_waste_usd"] == 0.0

    # Positive delta
    pos_event = events[1]
    assert pos_event["actual_kwh"] == 100.0
    assert pos_event["predicted_kwh"] == 80.0
    assert pos_event["delta_kwh"] == 20.0
    assert pos_event["estimated_waste_vnd"] == round(20.0 * get_tariff_rate_vnd(), 0)
    assert pos_event["estimated_waste_usd"] == round(20.0 * get_tariff_rate_usd(), 2)


def test_copilot_get_anomalies_and_forecast_summary():
    """Verify Copilot tools work against the unified pipeline."""
    # get_anomalies with limit
    top_2 = get_anomalies(limit=2)
    all_events = get_anomaly_events()
    assert len(top_2) == min(2, len(all_events))
    assert top_2 == all_events[:2]

    # query_forecast_summary
    fc_summary = query_forecast_summary()
    assert fc_summary["forecast_horizon"] == "24 hours"
    assert "expected_peak_kw" in fc_summary
    assert "peak_timestamp" in fc_summary
    assert "average_forecast_kwh" in fc_summary
    assert fc_summary["confidence_interval_95"].startswith("±")

    real_fc = predict_next_24h()
    assert fc_summary["expected_peak_kw"] == float(real_fc["predicted_kwh"].max())
    assert fc_summary["average_forecast_kwh"] == round(float(real_fc["predicted_kwh"].mean()), 1)

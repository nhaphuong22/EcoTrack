"""
Unit tests for EcoTrack Demo Scenario Generator:
- Validates exported scenario CSV files structure, columns, and data completeness
- Validates that HVAC night overrun points are detected as anomalies with MEDIUM/HIGH severity
- Validates that EVN peak hour demand spike points are detected as anomalies with HIGH severity
- Validates scenario generation using custom synthetic base DataFrames
"""

from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from src.data_pipeline.demo_scenarios import (
    export_demo_scenarios,
    generate_scenario_hvac_night_overrun,
    generate_scenario_peak_hour_spike,
    load_base_dataset,
)
from src.models.anomaly_service import AnomalyDetectionService, AnomalyEventRepository


@pytest.fixture(scope="session")
def base_clean_data():
    """Loads base clean building data."""
    return load_base_dataset()


@pytest.fixture
def isolated_anomaly_service():
    """Initializes AnomalyDetectionService with an independent event repository."""
    repo = AnomalyEventRepository()
    service = AnomalyDetectionService(event_repository=repo)
    return service, repo


def test_export_demo_scenarios_structure(tmp_path):
    """
    Verify exported scenario files have valid structure, complete columns,
    and zero missing values.
    """
    hvac_path, peak_path = export_demo_scenarios(output_dir=tmp_path)

    assert hvac_path.exists(), f"HVAC scenario CSV not created at: {hvac_path}"
    assert peak_path.exists(), f"Peak spike scenario CSV not created at: {peak_path}"

    for scenario_path in [hvac_path, peak_path]:
        df = pd.read_csv(scenario_path)
        # 1. Required columns
        assert list(df.columns) == ["timestamp", "meter_reading", "air_temperature"]
        # 2. Length check
        assert len(df) > 50
        # 3. No NaNs
        assert df.isna().sum().sum() == 0
        # 4. Numeric types
        assert pd.api.types.is_numeric_dtype(df["meter_reading"])
        assert pd.api.types.is_numeric_dtype(df["air_temperature"])
        # 5. Timestamp parsability
        parsed_ts = pd.to_datetime(df["timestamp"])
        assert not parsed_ts.isna().any()


def test_scenario_hvac_night_overrun_anomalies_detected(base_clean_data, isolated_anomaly_service):
    """
    Verify that HVAC night overrun scenario points (~750 kWh overnight)
    are flagged as anomalies with MEDIUM or HIGH severity by anomaly_service.
    """
    service, repo = isolated_anomaly_service
    repo.clear()

    df_hvac = generate_scenario_hvac_night_overrun(base_df=base_clean_data)
    df_hvac["dt"] = pd.to_datetime(df_hvac["timestamp"])

    # Locate the exact injected overrun points (modified relative to base_clean_data)
    overrun_indices = df_hvac.index[df_hvac["meter_reading"] != base_clean_data["meter_reading"]].tolist()

    assert len(overrun_indices) == 8, f"Expected 8 overrun hours, found {len(overrun_indices)}"

    detected_events = []
    for idx in overrun_indices:
        row = df_hvac.iloc[idx]
        reading = {
            "timestamp": str(row["timestamp"]),
            "meter_reading": float(row["meter_reading"]),
            "air_temperature": float(row["air_temperature"]),
            "building_id": "Hog_office_Betsy",
        }
        # Provide 24h context prior to anomaly point
        context_df = base_clean_data.iloc[max(0, idx - 24) : idx]
        event = service.process_reading(reading, historical_context_df=context_df)

        assert event is not None, f"Overrun reading at {reading['timestamp']} was NOT detected as an anomaly!"
        assert event["severity"] in ["MEDIUM", "HIGH"], f"Unexpected severity '{event['severity']}' for night overrun"
        assert event["actual_reading"] >= 700.0
        detected_events.append(event)

    assert len(detected_events) == len(overrun_indices)
    assert repo.count() == len(overrun_indices)


def test_scenario_peak_hour_spike_anomalies_detected(base_clean_data, isolated_anomaly_service):
    """
    Verify that EVN peak hour demand spike points (~2850 kWh)
    are flagged as anomalies with HIGH severity by anomaly_service.
    """
    service, repo = isolated_anomaly_service
    repo.clear()

    df_peak = generate_scenario_peak_hour_spike(base_df=base_clean_data)

    # Locate the exact injected peak spike points (modified relative to base_clean_data)
    spike_indices = df_peak.index[df_peak["meter_reading"] != base_clean_data["meter_reading"]].tolist()

    assert len(spike_indices) >= 3, f"Expected at least 3 peak spike hours, found {len(spike_indices)}"


    detected_events = []
    for idx in spike_indices:
        row = df_peak.iloc[idx]
        reading = {
            "timestamp": str(row["timestamp"]),
            "meter_reading": float(row["meter_reading"]),
            "air_temperature": float(row["air_temperature"]),
            "building_id": "Hog_office_Betsy",
        }
        context_df = base_clean_data.iloc[max(0, idx - 24) : idx]
        event = service.process_reading(reading, historical_context_df=context_df)

        assert event is not None, f"Peak spike at {reading['timestamp']} was NOT detected as an anomaly!"
        assert event["severity"] == "HIGH", f"Expected HIGH severity for peak surge, got '{event['severity']}'"
        assert event["actual_reading"] >= 2500.0
        detected_events.append(event)

    assert len(detected_events) == len(spike_indices)
    assert repo.count() == len(spike_indices)


def test_scenarios_generation_with_synthetic_base():
    """Verify scenario generation runs cleanly using a custom synthetic base DataFrame."""
    timestamps = pd.date_range("2026-06-01 00:00:00", periods=168, freq="1h")  # 1 full week
    np.random.seed(42)
    mock_base = pd.DataFrame({
        "timestamp": timestamps,
        "meter_reading": np.random.uniform(200.0, 400.0, size=len(timestamps)),
        "air_temperature": np.random.uniform(25.0, 35.0, size=len(timestamps)),
    })

    df_hvac = generate_scenario_hvac_night_overrun(base_df=mock_base)
    df_peak = generate_scenario_peak_hour_spike(base_df=mock_base)

    assert len(df_hvac) == len(mock_base)
    assert len(df_peak) == len(mock_base)
    assert df_hvac["meter_reading"].max() >= 700.0
    assert df_peak["meter_reading"].max() >= 2500.0

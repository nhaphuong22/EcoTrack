"""
Unit tests for EcoTrack Stream Data Worker and Anomaly Event Service:
- Validates sequential non-skipping telemetry emission from StreamDataWorker
- Validates worker start / stop asynchronous lifecycle
- Validates AnomalyDetectionService ignores normal baseline readings
- Validates AnomalyDetectionService detects artificial midnight spikes (e.g. 1000 kWh)
  and creates appropriate anomaly event records with severity categorization
"""

import asyncio
from pathlib import Path
import pandas as pd
import pytest

from src.data_pipeline.stream_worker import (
    MeterReadingRepository,
    StreamDataWorker,
)
from src.models.anomaly_service import (
    AnomalyDetectionService,
    AnomalyEventRepository,
)


@pytest.fixture
def clean_data_sample():
    """Reads first 50 rows of office_building_clean.csv or generates fallback."""
    backend_dir = Path(__file__).resolve().parents[1]
    csv_path = backend_dir / "data" / "processed" / "office_building_clean.csv"
    if csv_path.exists():
        return pd.read_csv(csv_path, nrows=50)

    # Fallback in fresh CI/CD if CSV is not checked into git
    timestamps = pd.date_range("2026-01-01 00:00:00", periods=50, freq="1h")
    return pd.DataFrame({
        "timestamp": timestamps.strftime("%Y-%m-%d %H:%M:%S"),
        "meter_reading": [240.0 + (i % 24) * 8.0 for i in range(50)],
        "air_temperature": [20.0 + (i % 24) * 0.4 for i in range(50)],
    })



@pytest.fixture
def custom_worker(clean_data_sample):
    """Initializes an isolated StreamDataWorker with an independent repository."""
    backend_dir = Path(__file__).resolve().parents[1]
    csv_path = backend_dir / "data" / "processed" / "office_building_clean.csv"
    repo = MeterReadingRepository()
    worker = StreamDataWorker(csv_path=csv_path, repository=repo, building_id="Test_Office_Betsy")
    return worker, repo


@pytest.fixture
def custom_anomaly_service():
    """Initializes an isolated AnomalyDetectionService with an independent repository."""
    event_repo = AnomalyEventRepository()
    service = AnomalyDetectionService(event_repository=event_repo)
    return service, event_repo


def test_stream_worker_sequential_no_skip(custom_worker, clean_data_sample):
    """
    Verify stream worker emits records sequentially without skipping rows.
    Checks index progression, timestamps, and readings against source CSV.
    """
    worker, repo = custom_worker
    worker.reset(start_index=0)

    emitted_readings = []
    num_steps = 8

    for step in range(num_steps):
        assert worker.current_index == step, f"Expected current_index={step}, got {worker.current_index}"
        reading = worker.emit_next_reading()
        emitted_readings.append(reading)

        # Verify against source CSV
        expected_row = clean_data_sample.iloc[step]
        expected_ts = str(expected_row["timestamp"])
        expected_reading = float(expected_row["meter_reading"])

        assert reading["timestamp"] == expected_ts, f"Timestamp mismatch at step {step}"
        assert abs(reading["meter_reading"] - expected_reading) < 1e-4, f"Reading mismatch at step {step}"
        assert reading["stream_index"] == step

    assert repo.count() == num_steps
    assert worker.current_index == num_steps


@pytest.mark.anyio
async def test_stream_worker_start_stop_lifecycle(custom_worker):
    """
    Verify async start and stop controls for the streaming background worker.
    """
    worker, repo = custom_worker
    worker.reset(start_index=0)

    # Start worker with rapid interval for unit testing
    status_start = await worker.start_streaming(interval_seconds=0.03, loop_forever=True)
    assert status_start["is_streaming"] is True

    # Allow worker to emit several readings
    await asyncio.sleep(0.12)

    status_running = worker.get_stream_status()
    assert status_running["is_streaming"] is True
    assert status_running["readings_emitted_count"] >= 2
    assert repo.count() >= 2

    # Stop worker
    status_stop = await worker.stop_streaming()
    assert status_stop["is_streaming"] is False

    emitted_at_stop = status_stop["readings_emitted_count"]
    await asyncio.sleep(0.06)
    # Confirm no further readings emitted after stopping
    assert worker.get_stream_status()["readings_emitted_count"] == emitted_at_stop


def test_anomaly_service_normal_reading(custom_anomaly_service, clean_data_sample):
    """
    Verify that ordinary baseline readings do not trigger anomaly events.
    """
    service, event_repo = custom_anomaly_service
    event_repo.clear()

    # Normal historical context (24 hours)
    hist_context = clean_data_sample.iloc[:24].copy()

    # Normal point from hour 24 (reading around ~223 kWh)
    normal_point = {
        "timestamp": str(clean_data_sample.iloc[24]["timestamp"]),
        "meter_reading": float(clean_data_sample.iloc[24]["meter_reading"]),
        "air_temperature": float(clean_data_sample.iloc[24]["air_temperature"]),
        "building_id": "Test_Office_Betsy",
    }

    event = service.process_reading(normal_point, historical_context_df=hist_context)

    # Must not be flagged as an anomaly
    assert event is None, f"Normal reading was falsely flagged as anomaly: {event}"
    assert event_repo.count() == 0


def test_anomaly_service_midnight_spike_detected(custom_anomaly_service, clean_data_sample):
    """
    Verify that an artificial midnight spike (e.g. 1000 kWh at 00:00:00)
    is detected by the service and generates an AnomalyEvent with correct severity.
    """
    service, event_repo = custom_anomaly_service
    event_repo.clear()

    # 24h normal history where midnight consumption was ~241 kWh
    hist_context = clean_data_sample.iloc[:24].copy()

    # Artificial surge: midnight load jumping to 1000.0 kWh
    spike_point = {
        "timestamp": "2016-01-02 00:00:00",
        "meter_reading": 1000.0,
        "air_temperature": -7.0,
        "building_id": "Test_Office_Betsy",
    }

    event = service.process_reading(spike_point, historical_context_df=hist_context)

    # 1. Anomaly event must be generated
    assert event is not None, "Midnight spike to 1000 kWh was NOT detected as anomaly!"

    # 2. Event fields verification
    assert event["actual_reading"] == 1000.0
    assert event["building_id"] == "Test_Office_Betsy"
    assert event["timestamp"] == "2016-01-02 00:00:00"
    assert isinstance(event["anomaly_score"], float)

    # 3. Severity categorization (spike to 1000 kWh is >4x baseline -> MEDIUM or HIGH)
    assert event["severity"] in ["MEDIUM", "HIGH"]

    # 4. Actionable suggestion
    assert "suggested_action" in event
    assert len(event["suggested_action"]) > 15
    assert any(term in event["suggested_action"].lower() for term in ["chiller", "hvac", "tải", "phụ tải"])

    # 5. Repository persistence
    assert event_repo.count() == 1
    stored_events = service.get_anomaly_events()
    assert len(stored_events) == 1
    assert stored_events[0]["id"] == event["id"]


def test_stream_worker_listener_anomaly_integration(custom_worker, custom_anomaly_service):
    """
    Verify end-to-end integration: StreamDataWorker notifies AnomalyDetectionService
    via listener callback when readings are emitted.
    """
    worker, _ = custom_worker
    service, event_repo = custom_anomaly_service
    event_repo.clear()
    worker.reset(start_index=0)

    # Register anomaly service listener
    received_readings = []

    def anomaly_listener(reading):
        received_readings.append(reading)
        service.process_reading(reading)

    worker.register_listener(anomaly_listener)

    # Emit 3 sequential readings
    for _ in range(3):
        worker.emit_next_reading()

    assert len(received_readings) == 3
    worker.unregister_listener(anomaly_listener)


def test_anomaly_service_missing_artifact_raises():
    """Missing isolation_forest.joblib -> raises ModelArtifactError naming the file, saves nothing."""
    import tempfile
    from src.data_pipeline.serving_frame import ModelArtifactError

    with tempfile.TemporaryDirectory() as empty_dir:
        missing_path = Path(empty_dir) / "isolation_forest.joblib"
        with pytest.raises(ModelArtifactError) as exc_info:
            AnomalyDetectionService(model_path=missing_path)
        assert "isolation_forest.joblib" in str(exc_info.value)
        assert not missing_path.exists()
        assert len(list(Path(empty_dir).iterdir())) == 0

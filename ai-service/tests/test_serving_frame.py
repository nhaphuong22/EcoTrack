import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
from starlette.testclient import TestClient

from src.agent.tools.energy_tools import query_metrics
from src.data_pipeline.serving_frame import (
    ModelArtifactError,
    ServingDataError,
    compute_energy_metrics,
    get_serving_frame,
    reset_serving_cache,
)
from src.main import app

REQUIRED_COLUMNS = [
    "timestamp",
    "meter_reading_kwh",
    "outdoor_temperature_c",
    "predicted_kwh",
    "residual",
    "lower_bound_95",
    "upper_bound_95",
    "anomaly_score",
    "is_anomaly",
    "severity",
]


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_plain_python_import_and_execution():
    """AC: Given the serving frame, when it is imported and called from a plain Python shell, it works without FastAPI."""
    frame = get_serving_frame()
    assert isinstance(frame, pd.DataFrame)
    assert len(frame) == 720
    assert list(frame.columns) == REQUIRED_COLUMNS


def test_serving_frame_columns_and_bounds():
    """Verify column names, row order ascending, bounds containing prediction, and floor at 0."""
    frame = get_serving_frame()
    assert len(frame) == 720
    assert list(frame.columns) == REQUIRED_COLUMNS

    # Rows ascending by time
    ts_list = pd.to_datetime(frame["timestamp"])
    assert ts_list.is_monotonic_increasing

    # Bounds contain prediction and lower bound floored at 0
    assert (frame["lower_bound_95"] <= frame["predicted_kwh"] + 1e-5).all()
    assert (frame["predicted_kwh"] <= frame["upper_bound_95"] + 1e-5).all()
    assert (frame["lower_bound_95"] >= 0.0).all()

    # Anomaly scores between 0 and 1
    assert (frame["anomaly_score"] >= 0.0).all()
    assert (frame["anomaly_score"] <= 1.0).all()


def test_api_metrics_endpoint(client):
    """Matrix: Metrics | Data and artifacts present | 200; same keys as today; values computed over last 720 hourly rows."""
    res = client.get("/internal/energy/metrics")
    assert res.status_code == 200
    data = res.json()
    expected_keys = {
        "building_id",
        "total_consumption_kwh",
        "peak_demand_kw",
        "predicted_baseline_kwh",
        "total_anomalies_detected",
        "estimated_waste_cost_vnd",
        "estimated_waste_cost_usd",
    }
    assert set(data.keys()) == expected_keys
    assert data["building_id"] == "office_tower_01"

    frame = get_serving_frame()
    assert data["total_consumption_kwh"] == round(float(frame["meter_reading_kwh"].sum()), 1)
    assert data["peak_demand_kw"] == round(float(frame["meter_reading_kwh"].max()), 1)
    assert data["predicted_baseline_kwh"] == round(float(frame["predicted_kwh"].sum()), 1)
    assert data["total_anomalies_detected"] == int(frame["is_anomaly"].sum())


def test_api_timeseries_endpoint(client):
    """Matrix: Time series | limit=24 | 200; count 24; rows ascending by time; relative_humidity_pct & anomaly_reason null."""
    res = client.get("/internal/energy/timeseries?limit=24")
    assert res.status_code == 200
    body = res.json()
    assert body["building_id"] == "office_tower_01"
    assert body["count"] == 24
    points = body["data"]
    assert len(points) == 24

    for pt in points:
        assert pt["timestamp"].endswith("Z")
        assert pt["relative_humidity_pct"] is None
        assert pt["anomaly_reason"] is None
        assert isinstance(pt["is_anomaly"], bool)
        assert pt["severity"] in ("Normal", "Medium", "Critical")
        assert 0.0 <= pt["anomaly_score"] <= 1.0

    # Verify timestamps are ascending
    ts_strings = [p["timestamp"] for p in points]
    assert ts_strings == sorted(ts_strings)


def test_replay_fixed_clock():
    """Matrix: Replay | Clock fixed at a Thursday 14:00 UTC | Last row's timestamp is that hour; source row is Thursday 14:00."""
    fixed_now = datetime(2026, 10, 8, 14, 0, 0, tzinfo=timezone.utc)  # 2026-10-08 is a Thursday
    frame = get_serving_frame(now=fixed_now)
    assert len(frame) == 720

    last_ts = frame["timestamp"].iloc[-1]
    assert last_ts == "2026-10-08T14:00:00Z"

    # All timestamps exactly 1 hour apart
    ts_series = pd.to_datetime(frame["timestamp"])
    diffs = ts_series.diff().dropna()
    assert (diffs == pd.Timedelta(hours=1)).all()


def test_hour_rollover_rebuilds_cache():
    """Matrix: Hour rollover | Clock advances one hour | The cached frame is rebuilt and ends at the new hour."""
    t1 = datetime(2026, 10, 8, 14, 0, 0, tzinfo=timezone.utc)
    frame1 = get_serving_frame(now=t1)
    assert frame1["timestamp"].iloc[-1] == "2026-10-08T14:00:00Z"

    t2 = datetime(2026, 10, 8, 15, 0, 0, tzinfo=timezone.utc)
    frame2 = get_serving_frame(now=t2)
    assert frame2["timestamp"].iloc[-1] == "2026-10-08T15:00:00Z"


def test_cached_artifacts_not_reloaded_from_disk():
    """AC: Given the frame was built once, when either endpoint is called again, dataset and artifacts are not reloaded."""
    reset_serving_cache()
    from src.models.train_models import load_dataset
    with patch("src.data_pipeline.serving_frame.load_dataset", wraps=load_dataset) as mock_load:
        get_serving_frame()
        get_serving_frame()
        assert mock_load.call_count == 1


def test_timeseries_limit_validation(client):
    """Matrix: Limit out of range | limit=0 or 721 | 422 from existing validation."""
    res_zero = client.get("/internal/energy/timeseries?limit=0")
    assert res_zero.status_code == 422

    res_large = client.get("/internal/energy/timeseries?limit=721")
    assert res_large.status_code == 422


def test_dataset_missing_503(client):
    """Matrix: Dataset missing | CSV path does not exist | 503 {"detail": ..., "code": "ERR_DATA_NOT_FOUND"} naming path."""
    reset_serving_cache()
    non_existent = Path("non_existent_data_path.csv").resolve()
    old_data_path = os.environ.get("ECOTRACK_DATA_PATH")
    os.environ["ECOTRACK_DATA_PATH"] = str(non_existent)
    try:
        res = client.get("/internal/energy/metrics")
        assert res.status_code == 503
        data = res.json()
        assert data["code"] == "ERR_DATA_NOT_FOUND"
        assert str(non_existent) in data["detail"]
        assert not non_existent.exists(), "No file should be created on error"
    finally:
        if old_data_path is not None:
            os.environ["ECOTRACK_DATA_PATH"] = old_data_path
        else:
            os.environ.pop("ECOTRACK_DATA_PATH", None)
        reset_serving_cache()


def test_artifact_missing_503(client):
    """Matrix: Artifact missing | A .joblib or metadata file is absent | 503 {"detail": ..., "code": "ERR_MODEL_NOT_FOUND"} naming file."""
    reset_serving_cache()
    with tempfile.TemporaryDirectory() as empty_dir:
        old_models_dir = os.environ.get("ECOTRACK_MODELS_DIR")
        os.environ["ECOTRACK_MODELS_DIR"] = empty_dir
        try:
            res = client.get("/internal/energy/metrics")
            assert res.status_code == 503
            data = res.json()
            assert data["code"] == "ERR_MODEL_NOT_FOUND"
            assert "xgboost_forecaster.joblib" in data["detail"]
            # No model trained or saved
            assert len(os.listdir(empty_dir)) == 0, "No model should be saved on missing artifact error"
        finally:
            if old_models_dir is not None:
                os.environ["ECOTRACK_MODELS_DIR"] = old_models_dir
            else:
                os.environ.pop("ECOTRACK_MODELS_DIR", None)
            reset_serving_cache()


def test_tariff_override():
    """Matrix: Tariff override | TARIFF_RATE_VND=2500 | estimated_waste_cost_vnd equals waste kWh * 2500."""
    frame = get_serving_frame()
    old_tariff = os.environ.get("TARIFF_RATE_VND")
    os.environ["TARIFF_RATE_VND"] = "2500"
    try:
        metrics = compute_energy_metrics(frame)
        waste_kwh = float(frame[frame["is_anomaly"]]["residual"].clip(lower=0).sum())
        expected_vnd = round(waste_kwh * 2500, 0)
        assert metrics["estimated_waste_cost_vnd"] == expected_vnd
    finally:
        if old_tariff is not None:
            os.environ["TARIFF_RATE_VND"] = old_tariff
        else:
            os.environ.pop("TARIFF_RATE_VND", None)


def test_copilot_tool_query_metrics():
    """Verify query_metrics tool returns matching metrics with copilot keys."""
    metrics = query_metrics()
    expected_tool_keys = {
        "building_id",
        "total_consumption_kwh",
        "peak_demand_kw",
        "baseline_kwh",
        "anomalies_detected",
        "estimated_waste_kwh",
        "estimated_waste_vnd",
        "estimated_waste_usd",
    }
    assert set(metrics.keys()) == expected_tool_keys
    assert metrics["building_id"] == "office_tower_01"

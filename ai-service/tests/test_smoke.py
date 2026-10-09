"""
EcoTrack AI Service - Smoke & Integration Tests
Validates ETL pipeline, ML forecaster, anomaly detector, and internal FastAPI AI endpoints.
"""
import math

import pytest
from starlette.testclient import TestClient

from src.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_api_health(client):
    """Verify health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_api_root(client):
    """Verify root info endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "operational"


def test_api_energy_metrics(client):
    """Verify internal energy summary metrics API."""
    response = client.get("/internal/energy/metrics")
    assert response.status_code == 200
    data = response.json()
    assert data["building_id"] == "office_tower_01"
    assert "total_consumption_kwh" in data
    assert "peak_demand_kw" in data
    assert "total_anomalies_detected" in data


def test_api_energy_timeseries(client):
    """Verify internal energy timeseries API."""
    response = client.get("/internal/energy/timeseries?limit=24")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 24
    assert len(data["data"]) == 24


def test_api_forecast_predict(client):
    """Verify internal 24h forecast endpoint: 24 forward points, ordered and bounded."""
    # Capture the last observed timestamp BEFORE the request so a UTC hour rollover
    # between the two cannot make forecast[0] equal a newer anchor (every forecast
    # timestamp stays strictly later than an anchor read no later than the request).
    from src.data_pipeline.serving_frame import get_serving_frame
    last_observed = get_serving_frame()["timestamp"].iloc[-1]

    response = client.get("/internal/forecast/predict")
    assert response.status_code == 200
    data = response.json()
    assert data["building_id"] == "office_tower_01"
    assert data["horizon_hours"] == 24
    forecast = data["forecast"]
    assert len(forecast) == 24

    timestamps = [pt["timestamp"] for pt in forecast]
    # ISO 8601 UTC with Z suffix
    assert all(ts.endswith("Z") for ts in timestamps)
    # Strictly increasing
    assert timestamps == sorted(timestamps)
    assert len(set(timestamps)) == 24
    # Every forecast timestamp is strictly later than the last observed reading
    assert all(ts > last_observed for ts in timestamps)

    # lower <= predicted <= upper and lower floored at 0; every point carries a finite temperature
    for pt in forecast:
        assert pt["lower_bound_95"] <= pt["predicted_kwh"] + 1e-6
        assert pt["predicted_kwh"] <= pt["upper_bound_95"] + 1e-6
        assert pt["lower_bound_95"] >= 0.0
        assert "outdoor_temperature_c" in pt
        assert isinstance(pt["outdoor_temperature_c"], (int, float)) and math.isfinite(pt["outdoor_temperature_c"])


def test_api_forecast_predict_warm_p95(client):
    """NFR3: warm endpoint answers under 300 ms at p95."""
    import time

    # Warm-up (pays the one-time cold-start load).
    assert client.get("/internal/forecast/predict").status_code == 200

    durations = []
    for _ in range(20):
        start = time.perf_counter()
        res = client.get("/internal/forecast/predict")
        durations.append((time.perf_counter() - start) * 1000.0)
        assert res.status_code == 200

    durations.sort()
    # 95th percentile (index 18 of 20 sorted samples).
    p95 = durations[int(0.95 * len(durations)) - 1]
    assert p95 < 300.0, f"p95 {p95:.1f} ms exceeded 300 ms budget"


def test_api_forecast_predict_insufficient_history(client):
    """<24h history -> endpoint returns 422 ERR_INSUFFICIENT_HISTORY envelope."""
    import pandas as pd
    import src.data_pipeline.serving_frame as sf

    # Warm the cache so the model/metadata are loaded; the short frame is the only failure.
    sf.get_serving_frame()
    short_frame = pd.DataFrame({
        "timestamp": [f"2026-01-01T{h:02d}:00:00Z" for h in range(10)],
        "meter_reading_kwh": [100.0 + h for h in range(10)],
        "outdoor_temperature_c": [20.0 + h for h in range(10)],
    })

    original = sf.get_serving_frame
    try:
        sf.get_serving_frame = lambda now=None: short_frame
        res = client.get("/internal/forecast/predict")
    finally:
        sf.get_serving_frame = original
        sf.reset_serving_cache()

    assert res.status_code == 422
    body = res.json()
    assert body["code"] == "ERR_INSUFFICIENT_HISTORY"
    assert "24" in body["detail"]


def test_api_forecast_predict_missing_artifact(client):
    """Missing XGBoost artifact -> endpoint returns 503 ERR_MODEL_NOT_FOUND naming the file."""
    import os
    import tempfile
    import src.data_pipeline.serving_frame as sf

    sf.reset_serving_cache()
    with tempfile.TemporaryDirectory() as empty_dir:
        old_models_dir = os.environ.get("ECOTRACK_MODELS_DIR")
        os.environ["ECOTRACK_MODELS_DIR"] = empty_dir
        try:
            res = client.get("/internal/forecast/predict")
            assert res.status_code == 503
            body = res.json()
            assert body["code"] == "ERR_MODEL_NOT_FOUND"
            assert "xgboost_forecaster.joblib" in body["detail"]
            assert len(os.listdir(empty_dir)) == 0, "no model should be trained or saved on error"
        finally:
            if old_models_dir is not None:
                os.environ["ECOTRACK_MODELS_DIR"] = old_models_dir
            else:
                os.environ.pop("ECOTRACK_MODELS_DIR", None)
            sf.reset_serving_cache()


def test_api_forecast_dataset_missing_503(client):
    """Matrix: Dataset missing -> 503 {"code": "ERR_DATA_NOT_FOUND"} on the forecast endpoint."""
    import os
    from pathlib import Path
    from src.data_pipeline.serving_frame import reset_serving_cache

    reset_serving_cache()
    non_existent = Path("non_existent_forecast_data.csv").resolve()
    old_data_path = os.environ.get("ECOTRACK_DATA_PATH")
    os.environ["ECOTRACK_DATA_PATH"] = str(non_existent)
    try:
        response = client.get("/internal/forecast/predict")
        assert response.status_code == 503
        assert response.json()["code"] == "ERR_DATA_NOT_FOUND"
    finally:
        if old_data_path is not None:
            os.environ["ECOTRACK_DATA_PATH"] = old_data_path
        else:
            os.environ.pop("ECOTRACK_DATA_PATH", None)
        reset_serving_cache()


def test_api_anomalies_detect(client):
    """Verify internal anomaly detection endpoint and agreement with energy metrics."""
    from src.config import get_tariff_rate_usd, get_tariff_rate_vnd

    metrics_resp = client.get("/internal/energy/metrics")
    assert metrics_resp.status_code == 200
    metrics_data = metrics_resp.json()

    response = client.get("/internal/anomalies/detect")
    assert response.status_code == 200
    events = response.json()
    assert isinstance(events, list)

    # Agreement with /internal/energy/metrics total_anomalies_detected
    assert len(events) == metrics_data["total_anomalies_detected"]

    # Also verify POST method behaves identically
    post_resp = client.post("/internal/anomalies/detect")
    assert post_resp.status_code == 200
    assert len(post_resp.json()) == len(events)

    if events:
        first = events[0]
        expected_keys = {
            "id", "building_id", "timestamp", "subsystem", "severity",
            "anomaly_score", "actual_kwh", "predicted_kwh", "delta_kwh",
            "outdoor_temp_c", "estimated_waste_vnd", "estimated_waste_usd",
            "status", "description", "suggested_action"
        }
        assert expected_keys.issubset(set(first.keys()))

        # Timestamps are ISO 8601 UTC ending with Z
        assert all(ev["timestamp"].endswith("Z") for ev in events)

        # Severities are valid
        valid_severities = {"Normal", "Medium", "Critical", "NORMAL", "MEDIUM", "CRITICAL"}
        assert all(ev["severity"] in valid_severities for ev in events)

        # Waste calculations tie to tariffs
        for ev in events:
            assert ev["delta_kwh"] >= 0.0
            assert ev["estimated_waste_vnd"] == round(ev["delta_kwh"] * get_tariff_rate_vnd(), 0)
            assert ev["estimated_waste_usd"] == round(ev["delta_kwh"] * get_tariff_rate_usd(), 2)


def test_api_anomalies_detect_missing_artifact(client):
    """Missing Isolation Forest artifact -> 503 ERR_MODEL_NOT_FOUND naming the file."""
    import os
    import shutil
    import tempfile
    from pathlib import Path
    import src.data_pipeline.serving_frame as sf

    sf.reset_serving_cache()
    current_models_dir = Path(os.environ["ECOTRACK_MODELS_DIR"])
    with tempfile.TemporaryDirectory() as empty_dir:
        temp_dir = Path(empty_dir)
        for item in current_models_dir.iterdir():
            if item.name != "isolation_forest.joblib":
                shutil.copy2(item, temp_dir / item.name)

        old_models_dir = os.environ.get("ECOTRACK_MODELS_DIR")
        os.environ["ECOTRACK_MODELS_DIR"] = str(temp_dir)
        try:
            res = client.get("/internal/anomalies/detect")
            assert res.status_code == 503
            body = res.json()
            assert body["code"] == "ERR_MODEL_NOT_FOUND"
            assert "isolation_forest.joblib" in body["detail"]
            assert not (temp_dir / "isolation_forest.joblib").exists(), "no model should be trained or saved on error"
        finally:
            if old_models_dir is not None:
                os.environ["ECOTRACK_MODELS_DIR"] = old_models_dir
            else:
                os.environ.pop("ECOTRACK_MODELS_DIR", None)
            sf.reset_serving_cache()


def test_api_anomalies_detect_missing_dataset(client):
    """Missing dataset -> 503 ERR_DATA_NOT_FOUND naming the path."""
    import os
    from pathlib import Path
    import src.data_pipeline.serving_frame as sf

    sf.reset_serving_cache()
    old_data_path = os.environ.get("ECOTRACK_DATA_PATH")
    os.environ["ECOTRACK_DATA_PATH"] = str(Path("non_existent_anom_data.csv").resolve())
    try:
        res = client.get("/internal/anomalies/detect")
        assert res.status_code == 503
        body = res.json()
        assert body["code"] == "ERR_DATA_NOT_FOUND"
    finally:
        if old_data_path is not None:
            os.environ["ECOTRACK_DATA_PATH"] = old_data_path
        else:
            os.environ.pop("ECOTRACK_DATA_PATH", None)
        sf.reset_serving_cache()

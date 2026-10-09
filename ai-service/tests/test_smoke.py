"""
EcoTrack AI Service - Smoke & Integration Tests
Validates ETL pipeline, ML forecaster, anomaly detector, and internal FastAPI AI endpoints.
"""
import pytest
from starlette.testclient import TestClient

from src.main import app
from src.data_pipeline.bdg2_loader import data_loader
from src.models.forecaster_xgboost import energy_forecaster
from src.models.anomaly_isolation_forest import anomaly_detector


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_data_pipeline_loader():
    """Verify Building Data Genome 2 loader produces valid DataFrame."""
    df = data_loader.get_or_create_data()
    assert df is not None
    assert len(df) > 0
    assert "timestamp" in df.columns
    assert "meter_reading_kwh" in df.columns
    assert "outdoor_temperature_c" in df.columns


def test_forecaster_predictor():
    """Verify XGBoost forecaster generates baseline and 95% confidence intervals."""
    df = data_loader.get_or_create_data()
    df_fc = energy_forecaster.predict_horizon(df)
    assert "predicted_kwh" in df_fc.columns
    assert "lower_bound_95" in df_fc.columns
    assert "upper_bound_95" in df_fc.columns
    assert "residual" in df_fc.columns
    assert len(df_fc) == len(df)
    assert (df_fc["predicted_kwh"] >= 0).all()


def test_anomaly_detector():
    """Verify Isolation Forest anomaly detector flags anomalies."""
    df = data_loader.get_or_create_data()
    df_fc = energy_forecaster.predict_horizon(df)
    df_anom = anomaly_detector.detect_anomalies(df_fc)
    assert "anomaly_score" in df_anom.columns
    assert "is_anomaly" in df_anom.columns
    assert "severity" in df_anom.columns
    assert df_anom["is_anomaly"].sum() > 0


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
    response = client.get("/internal/forecast/predict")
    assert response.status_code == 200
    data = response.json()
    assert data["building_id"] == "office_tower_01"
    assert data["horizon_hours"] == 24
    forecast = data["forecast"]
    assert len(forecast) == 24

    # Last observed timestamp from the serving frame (what the timeseries endpoint serves).
    from src.data_pipeline.serving_frame import get_serving_frame
    last_observed = get_serving_frame()["timestamp"].iloc[-1]

    timestamps = [pt["timestamp"] for pt in forecast]
    # ISO 8601 UTC with Z suffix
    assert all(ts.endswith("Z") for ts in timestamps)
    # Strictly increasing
    assert timestamps == sorted(timestamps)
    assert len(set(timestamps)) == 24
    # Every forecast timestamp is strictly later than the last observed reading
    assert all(ts > last_observed for ts in timestamps)

    # lower <= predicted <= upper and lower floored at 0
    for pt in forecast:
        assert pt["lower_bound_95"] <= pt["predicted_kwh"] + 1e-6
        assert pt["predicted_kwh"] <= pt["upper_bound_95"] + 1e-6
        assert pt["lower_bound_95"] >= 0.0


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
    """Verify internal anomaly detection endpoint."""
    from src.config import get_tariff_rate_vnd
    response = client.get("/internal/anomalies/detect")
    assert response.status_code == 200
    events = response.json()
    assert isinstance(events, list)
    assert len(events) > 0
    assert "severity" in events[0]
    first = events[0]
    assert first["estimated_waste_vnd"] == round(first["delta_kwh"] * get_tariff_rate_vnd(), 0)

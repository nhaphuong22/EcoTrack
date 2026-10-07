"""
EcoTrack Backend - Smoke & Integration Tests
Validates ETL pipeline, ML forecaster, anomaly detector, and core FastAPI endpoints.
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
    """Verify energy summary metrics API."""
    response = client.get("/api/v1/energy/metrics")
    assert response.status_code == 200
    data = response.json()
    assert data["building_id"] == "office_tower_01"
    assert "total_consumption_kwh" in data
    assert "peak_demand_kw" in data
    assert "total_anomalies_detected" in data


def test_api_energy_timeseries(client):
    """Verify energy timeseries API."""
    response = client.get("/api/v1/energy/timeseries?limit=24")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 24
    assert len(data["data"]) == 24


def test_api_forecast_predict(client):
    """Verify 24h forecast endpoint."""
    response = client.get("/api/v1/forecast/predict")
    assert response.status_code == 200
    data = response.json()
    assert data["building_id"] == "office_tower_01"
    assert data["horizon_hours"] == 24
    assert len(data["forecast"]) == 24


def test_api_anomalies_events(client):
    """Verify anomaly events endpoint."""
    response = client.get("/api/v1/anomalies/events")
    assert response.status_code == 200
    events = response.json()
    assert isinstance(events, list)
    assert len(events) > 0
    assert "severity" in events[0]


def test_internal_ai_endpoints(client):
    """Verify internal endpoints consumed by Express gateway."""
    # 1. Forecast
    fc_resp = client.get("/internal/forecast/predict")
    assert fc_resp.status_code == 200
    assert len(fc_resp.json()["forecast"]) == 24

    # 2. Metrics
    met_resp = client.get("/internal/energy/metrics")
    assert met_resp.status_code == 200
    assert "total_consumption_kwh" in met_resp.json()

    # 3. Anomaly detection
    anom_resp = client.get("/internal/anomalies/detect")
    assert anom_resp.status_code == 200
    assert isinstance(anom_resp.json(), list)
    assert len(anom_resp.json()) > 0

import pandas as pd
from unittest.mock import patch
from fastapi.testclient import TestClient

from src.data_pipeline.serving_frame import get_anomaly_events
from src.main import app


def observation(timestamp="2026-10-31T10:00:00Z", actual=100.0):
    return {"timestamp": timestamp, "meter_reading_kwh": actual,
            "predicted_kwh": 60.0, "outdoor_temperature_c": 28.0,
            "severity": "Critical", "anomaly_score": 0.9, "is_anomaly": True}


def test_incident_identity_survives_position_change_but_not_a_different_observation():
    original = get_anomaly_events(pd.DataFrame([observation()], index=[719]))[0]
    moved = get_anomaly_events(pd.DataFrame([observation()], index=[718]))[0]
    newer = get_anomaly_events(pd.DataFrame([observation("2026-10-31T11:00:00Z")], index=[719]))[0]
    different_replay = get_anomaly_events(pd.DataFrame([observation(actual=120.0)], index=[719]))[0]
    assert original["id"] == moved["id"]
    assert original["id"] != newer["id"]
    assert original["id"] != different_replay["id"]
    assert len(original["id"]) <= 50


def test_copilot_rejects_another_building_instead_of_using_office_measurements():
    with patch("src.api.routers.copilot.copilot_orchestrator.process_chat") as process:
        with TestClient(app, headers={"X-Internal-Token": "test-internal-token"}) as client:
            response = client.post("/internal/copilot/chat", json={
                "message": "metrics", "building_id": "Hog_office_Betsy", "history": [],
            })
        assert response.status_code == 422
        process.assert_not_called()

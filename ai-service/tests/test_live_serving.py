from datetime import datetime, timedelta, timezone
import os

from fastapi.testclient import TestClient

from src.main import app


def _hourly_series(hours: int = 30):
    base = datetime(2026, 11, 16, 0, 0, tzinfo=timezone.utc)
    rows = []
    for h in range(hours):
        ts = base + timedelta(hours=h)
        rows.append({
            "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "meter_reading_kwh": 160.0 + (h % 24) * 4.5,
            "outdoor_temperature_c": 25.0 + (h % 24) * 0.3,
        })
    return rows


def _auth_headers():
    token = os.getenv("INTERNAL_API_KEY", "test-internal-token")
    return {"X-Internal-Token": token}


def test_live_db_forecast_and_timeseries_endpoints(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_KEY", "live-test-token")
    monkeypatch.setenv("ECOTRACK_DISABLE_MLFLOW", "1")
    series = _hourly_series(30)

    with TestClient(app) as client:
        fc_resp = client.post(
            "/internal/forecast/predict",
            headers=_auth_headers(),
            json={"building_id": "office_tower_01", "recent_readings": series},
        )
        assert fc_resp.status_code == 200
        fc = fc_resp.json()
        assert fc["source"] == "live_db"
        assert fc["horizon_hours"] == 24
        assert len(fc["forecast"]) == 24
        assert fc["forecast"][0]["timestamp"] == "2026-11-17T06:00:00Z"
        assert fc["forecast"][0]["upper_bound_95"] > fc["forecast"][0]["lower_bound_95"]

        ts_resp = client.post(
            "/internal/energy/timeseries?limit=5",
            headers=_auth_headers(),
            json={"building_id": "office_tower_01", "recent_readings": series},
        )
        assert ts_resp.status_code == 200
        ts_body = ts_resp.json()
        assert ts_body["count"] == 5
        assert len(ts_body["data"]) == 5
        assert "predicted_kwh" in ts_body["data"][0]

        # Calibrated small-scale office series (70..286 kWh) must remain near building scale.
        small_hours = [
            78, 74, 72, 70, 72, 82, 118, 175, 235, 265, 278, 268,
            210, 248, 282, 286, 272, 228, 168, 132, 112, 96, 86, 80,
        ]
        small_series = [
            {
                "timestamp": (datetime(2026, 11, 15, 19, 0, tzinfo=timezone.utc) + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "meter_reading_kwh": float(small_hours[i % 24]),
                "outdoor_temperature_c": 24.5 + (i % 12) * 0.6,
            }
            for i in range(48)
        ]
        fc_small = client.post(
            "/internal/forecast/predict",
            headers=_auth_headers(),
            json={"building_id": "office_tower_01", "recent_readings": small_series},
        )
        assert fc_small.status_code == 200
        preds = [pt["predicted_kwh"] for pt in fc_small.json()["forecast"]]
        assert max(preds) < 500.0
        assert min(preds) > 20.0


def test_live_anomaly_scoring_detects_2_5x_spike_and_ignores_normal_tick(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_KEY", "live-test-token")
    monkeypatch.setenv("ECOTRACK_DISABLE_MLFLOW", "1")

    with TestClient(app) as client:
        resp = client.post(
            "/internal/anomalies/score",
            headers=_auth_headers(),
            json={
                "items": [
                    {
                        "building_id": "office_tower_01",
                        "zone_id": "z1",
                        "meter_id": "meter-z1",
                        "timestamp": "2026-11-18T07:00:00Z",
                        "meter_reading_kwh": 0.015,
                        "interval_seconds": 3.0,
                        "outdoor_temperature_c": 29.0,
                        "recent_meter_hourly_kwhs": [17.8, 18.0, 18.2, 17.9],
                        "recent_building_hourly_kwhs": [180.0] * 24,
                    },
                    {
                        "building_id": "office_tower_01",
                        "zone_id": "z3",
                        "meter_id": "meter-z3",
                        "timestamp": "2026-11-18T07:00:00Z",
                        "meter_reading_kwh": 0.0375,  # 45.0 kWh/h vs 18.0 expected (2.5x)
                        "interval_seconds": 3.0,
                        "outdoor_temperature_c": 37.5,
                        "recent_meter_hourly_kwhs": [18.0, 18.1, 17.9, 18.0],
                        "recent_building_hourly_kwhs": [180.0] * 24,
                    },
                ]
            },
        )
    assert resp.status_code == 200
    events = resp.json()
    assert len(events) == 1
    ev = events[0]
    assert ev["zone_id"] == "z3"
    assert ev["meter_id"] == "meter-z3"
    assert ev["severity"] == "CRITICAL"
    assert ev["actual_kwh"] == 45.0
    assert ev["delta_kwh"] > 20.0
    assert ev["estimated_waste_vnd"] > 0

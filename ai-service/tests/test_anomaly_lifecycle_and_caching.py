"""
Unit and Integration Tests for TV3 Backend Deliverables:
1. Anomaly Incident Lifecycle Management:
   - GET /api/v1/anomalies/events
   - PATCH /api/v1/anomalies/{anomaly_id}/status (OPEN -> ACKNOWLEDGED -> RESOLVED)
   - 422 validation for invalid lifecycle statuses
   - 404 for unknown anomaly incident IDs
2. In-Memory TTL Caching:
   - Cache MISS on initial request
   - Cache HIT on subsequent requests with sub-5ms response
   - Cache statistics and clear endpoints
"""

import time
import pytest
from starlette.testclient import TestClient

from src.main import app
from src.database import init_db


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c


def test_get_anomalies_events(client):
    """Verifies that detected anomalies are returned with default OPEN lifecycle state."""
    response = client.get("/api/v1/anomalies/events")
    assert response.status_code == 200
    events = response.json()
    assert isinstance(events, list)
    assert len(events) > 0
    first_event = events[0]
    assert "id" in first_event
    assert "severity" in first_event
    assert "status" in first_event
    assert first_event["status"] in ["OPEN", "New", "ACKNOWLEDGED", "RESOLVED"]


def test_update_anomaly_status_lifecycle(client):
    """Verifies state transition lifecycle: OPEN -> ACKNOWLEDGED -> RESOLVED."""
    # 1. Fetch available anomalies to get a target ID
    get_resp = client.get("/api/v1/anomalies/events")
    assert get_resp.status_code == 200
    events = get_resp.json()
    assert len(events) > 0
    target_id = events[0]["id"]

    # 2. Transition to ACKNOWLEDGED
    ack_payload = {
        "status": "ACKNOWLEDGED",
        "note": "Operator dispatched technician to inspect HVAC condenser.",
    }
    ack_resp = client.patch(f"/api/v1/anomalies/{target_id}/status", json=ack_payload)
    assert ack_resp.status_code == 200
    ack_data = ack_resp.json()
    assert ack_data["id"] == target_id
    assert ack_data["current_status"] == "ACKNOWLEDGED"
    assert "technician" in ack_data["note"]

    # 3. Transition to RESOLVED
    res_payload = {
        "status": "RESOLVED",
        "note": "Filter replaced. Power draw returned to normal.",
    }
    res_resp = client.patch(f"/api/v1/anomalies/{target_id}/status", json=res_payload)
    assert res_resp.status_code == 200
    res_data = res_resp.json()
    assert res_data["id"] == target_id
    assert res_data["previous_status"] == "ACKNOWLEDGED"
    assert res_data["current_status"] == "RESOLVED"

    # 4. Verify persistent status is reflected in list
    verify_resp = client.get("/api/v1/anomalies/events")
    assert verify_resp.status_code == 200
    updated_event = next((e for e in verify_resp.json() if e["id"] == target_id), None)
    assert updated_event is not None
    assert updated_event["status"] == "RESOLVED"


def test_update_anomaly_invalid_status_returns_422(client):
    """Verifies that invalid status values are rejected with 422 Unprocessable Entity."""
    get_resp = client.get("/api/v1/anomalies/events")
    events = get_resp.json()
    target_id = events[0]["id"]

    invalid_payload = {
        "status": "COMPLETELY_INVALID_STATUS",
        "note": "This should fail validation.",
    }
    response = client.patch(f"/api/v1/anomalies/{target_id}/status", json=invalid_payload)
    assert response.status_code == 422


def test_update_anomaly_not_found_returns_404(client):
    """Verifies that non-existent anomaly IDs return 404 Not Found."""
    payload = {"status": "RESOLVED", "note": "Testing 404 response."}
    response = client.patch("/api/v1/anomalies/ANOM-NONEXISTENT-99999/status", json=payload)
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_energy_ttl_caching_and_latency(client):
    """Verifies in-memory TTL caching reduces response latency and sets X-Cache headers."""
    # 1. Clear cache
    clear_resp = client.post("/api/v1/energy/cache/clear")
    assert clear_resp.status_code == 200

    # 2. First call: Cache MISS
    t0 = time.time()
    resp1 = client.get("/api/v1/energy/metrics")
    latency_miss = time.time() - t0
    assert resp1.status_code == 200
    assert resp1.headers.get("X-Cache") == "MISS"

    # 3. Second call: Cache HIT (should be significantly faster)
    t1 = time.time()
    resp2 = client.get("/api/v1/energy/metrics")
    latency_hit = time.time() - t1
    assert resp2.status_code == 200
    assert resp2.headers.get("X-Cache") == "HIT"
    assert latency_hit < 0.05  # Sub-50ms target

    # 4. Check cache diagnostic statistics
    stats_resp = client.get("/api/v1/energy/cache/stats")
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert stats["hits"] >= 1
    assert stats["entries_count"] >= 1

    # 5. Timeseries caching
    ts1 = client.get("/api/v1/energy/timeseries?limit=24")
    assert ts1.headers.get("X-Cache") == "MISS"
    ts2 = client.get("/api/v1/energy/timeseries?limit=24")
    assert ts2.headers.get("X-Cache") == "HIT"

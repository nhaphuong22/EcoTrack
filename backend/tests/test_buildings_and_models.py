"""
Unit and Integration Tests for Sprint 1 Deliverables:
- SQLAlchemy Models: Building, MeterReading, AnomalyEvent, Conversation
- Building and Historical Telemetry APIs:
  - GET /api/v1/buildings
  - GET /api/v1/buildings/{building_id}
  - POST /api/v1/buildings
  - GET /api/v1/buildings/{building_id}/history
"""

from datetime import datetime, timezone
import pytest
from starlette.testclient import TestClient

from src.main import app
from src.database import SessionLocal, init_db
from src.models import Building, MeterReading, AnomalyEvent, Conversation


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def db_session():
    init_db()
    session = SessionLocal()
    yield session
    session.close()


def test_sqlalchemy_models_crud(db_session):
    """Verifies that all 4 SQLAlchemy entities can be created, persisted, and queried."""
    # 1. Create Building
    b_id = f"test_tower_{int(datetime.now().timestamp())}"
    building = Building(
        id=b_id,
        name="Test Monitored Tower",
        building_type="Education",
        total_area_sqm=5000.0,
        location="Danang, Vietnam",
        timezone="Asia/Ho_Chi_Minh",
    )
    db_session.add(building)
    db_session.commit()

    queried_building = db_session.query(Building).filter(Building.id == b_id).first()
    assert queried_building is not None
    assert queried_building.name == "Test Monitored Tower"

    # 2. Create MeterReading
    now = datetime.now(timezone.utc)
    reading = MeterReading(
        building_id=b_id,
        timestamp=now,
        meter_reading_kwh=320.5,
        outdoor_temperature_c=28.4,
        relative_humidity_pct=75.0,
    )
    db_session.add(reading)
    db_session.commit()

    queried_reading = db_session.query(MeterReading).filter(MeterReading.building_id == b_id).first()
    assert queried_reading is not None
    assert queried_reading.meter_reading_kwh == 320.5

    # 3. Create AnomalyEvent
    event = AnomalyEvent(
        id=f"ANOM-TEST-{b_id}",
        building_id=b_id,
        timestamp=now,
        actual_reading=520.0,
        anomaly_score=-0.08,
        severity="CRITICAL",
        suggested_action="Inspect chiller unit C-1 immediately.",
        status="OPEN",
    )
    db_session.add(event)
    db_session.commit()

    queried_event = db_session.query(AnomalyEvent).filter(AnomalyEvent.id == f"ANOM-TEST-{b_id}").first()
    assert queried_event is not None
    assert queried_event.severity == "CRITICAL"

    # 4. Create Conversation
    conv = Conversation(
        building_id=b_id,
        session_id="session_test_01",
        role="user",
        message="Is energy consumption normal today?",
    )
    db_session.add(conv)
    db_session.commit()

    queried_conv = db_session.query(Conversation).filter(Conversation.session_id == "session_test_01").first()
    assert queried_conv is not None
    assert queried_conv.role == "user"


def test_api_get_buildings(client):
    """Verifies GET /api/v1/buildings endpoint returns list of buildings."""
    response = client.get("/api/v1/buildings")
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "buildings" in data
    assert data["total"] >= 1
    assert any(b["id"] in ["office_tower_01", "Hog_office_Betsy"] for b in data["buildings"])


def test_api_create_and_get_building(client):
    """Verifies POST and GET for a specific building."""
    new_id = f"lab_building_{int(datetime.now().timestamp())}"
    payload = {
        "id": new_id,
        "name": "EcoTrack AI Laboratory",
        "building_type": "Research & Lab",
        "total_area_sqm": 8400.0,
        "location": "Hanoi, Vietnam",
        "timezone": "Asia/Ho_Chi_Minh",
    }

    create_resp = client.post("/api/v1/buildings", json=payload)
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["id"] == new_id
    assert created["name"] == "EcoTrack AI Laboratory"

    # Query by ID
    get_resp = client.get(f"/api/v1/buildings/{new_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == new_id


def test_api_get_building_history(client):
    """Verifies GET /api/v1/buildings/{building_id}/history returns time-series data."""
    response = client.get("/api/v1/buildings/office_tower_01/history?limit=24")
    assert response.status_code == 200
    data = response.json()
    assert data["building_id"] == "office_tower_01"
    assert "count" in data
    assert "data" in data
    assert isinstance(data["data"], list)

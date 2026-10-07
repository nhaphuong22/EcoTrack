"""
Building & Historical Telemetry API Router for EcoTrack
Implements Sprint 1 endpoints:
1. GET /api/v1/buildings - Get list of monitored buildings (auto-seeds defaults if empty)
2. GET /api/v1/buildings/{building_id} - Get specific building details
3. GET /api/v1/buildings/{building_id}/history - Get historical energy consumption time-series
4. POST /api/v1/buildings - Register a new building
"""

from datetime import datetime, timedelta, timezone
import logging
import math
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
import pandas as pd
from sqlalchemy.orm import Session

from src.api.schemas.building import (
    BuildingCreate,
    BuildingHistoryResponse,
    BuildingListResponse,
    BuildingResponse,
    HistoricalReadingPoint,
)
from src.database import get_db
from src.models.db_models import Building, MeterReading

logger = logging.getLogger("BuildingsRouter")
router = APIRouter(prefix="/api/v1/buildings", tags=["Buildings & Telemetry"])


def _seed_default_buildings_if_needed(db: Session) -> None:
    """Ensures standard benchmark buildings exist in the database."""
    benchmark_ids = ["office_tower_01", "Hog_office_Betsy"]
    existing_ids = {
        b[0]
        for b in db.query(Building.id).filter(Building.id.in_(benchmark_ids)).all()
    }

    defaults = [
        Building(
            id="office_tower_01",
            name="EcoTrack Headquarter Tower",
            building_type="Commercial Office",
            total_area_sqm=15200.0,
            location="Hanoi, Vietnam",
            timezone="Asia/Ho_Chi_Minh",
        ),
        Building(
            id="Hog_office_Betsy",
            name="Hog Betsy Benchmark Office (BDG2)",
            building_type="Office",
            total_area_sqm=18450.0,
            location="Singapore",
            timezone="Asia/Singapore",
        ),
    ]

    added = False
    for b in defaults:
        if b.id not in existing_ids:
            db.add(b)
            added = True

    if added:
        db.commit()
        for b in defaults:
            _seed_initial_readings_if_needed(db, building_id=b.id)


def _seed_initial_readings_if_needed(db: Session, building_id: str, sample_hours: int = 168) -> None:
    """Populates historical readings from clean CSV or realistic synthetic profile if empty."""
    existing_readings = db.query(MeterReading).filter(MeterReading.building_id == building_id).count()
    if existing_readings >= 24:
        return

    records = []
    # 1. Try reading from clean processed CSV if available
    csv_path = Path(__file__).resolve().parents[3] / "data" / "processed" / "office_building_clean.csv"
    if csv_path.exists():
        try:
            df = pd.read_csv(csv_path)
            if not df.empty:
                slice_df = df.tail(sample_hours)
                for _, row in slice_df.iterrows():
                    ts_str = str(row.get("timestamp"))
                    try:
                        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    except Exception:
                        dt = datetime.now(timezone.utc)

                    kwh = float(row.get("meter_reading", row.get("meter_reading_kwh", 150.0)))
                    temp = float(row.get("air_temperature", row.get("outdoor_temperature_c", 25.0)))
                    humidity = float(row.get("relative_humidity_pct", 70.0)) if "relative_humidity_pct" in row else None

                    records.append(
                        MeterReading(
                            building_id=building_id,
                            timestamp=dt,
                            meter_reading_kwh=kwh,
                            outdoor_temperature_c=temp,
                            relative_humidity_pct=humidity,
                        )
                    )
        except Exception as exc:
            logger.warning("Could not parse CSV for seeding '%s': %s", building_id, exc)

    # 2. Fallback: generate realistic benchmark telemetry (last 72h)
    if not records:
        base_time = datetime.now(timezone.utc) - timedelta(hours=72)
        for h in range(72):
            t = base_time + timedelta(hours=h)
            hour_of_day = t.hour
            # Diurnal office energy pattern (low at night ~80 kW, peak at day ~240 kW)
            diurnal_factor = math.sin((hour_of_day - 6) * math.pi / 12) if 6 <= hour_of_day <= 18 else -0.5
            kwh = round(160.0 + diurnal_factor * 80.0 + (h % 5), 2)
            temp = round(26.0 + diurnal_factor * 5.0, 1)

            records.append(
                MeterReading(
                    building_id=building_id,
                    timestamp=t,
                    meter_reading_kwh=max(kwh, 50.0),
                    outdoor_temperature_c=temp,
                    relative_humidity_pct=72.0,
                )
            )

    try:
        db.bulk_save_objects(records)
        db.commit()
        logger.info("Successfully seeded %d historical readings for building '%s'.", len(records), building_id)
    except Exception as exc:
        db.rollback()
        logger.warning("Failed saving readings for '%s': %s", building_id, exc)


@router.get("", response_model=BuildingListResponse, summary="Get list of all monitored buildings")
def get_buildings(db: Session = Depends(get_db)):
    """
    Returns the complete list of monitored buildings.
    Automatically populates benchmark buildings on first startup if empty.
    """
    _seed_default_buildings_if_needed(db)
    buildings = db.query(Building).order_by(Building.created_at.asc()).all()
    return BuildingListResponse(
        total=len(buildings),
        buildings=[BuildingResponse.model_validate(b) for b in buildings],
    )


@router.get("/{building_id}", response_model=BuildingResponse, summary="Get building by ID")
def get_building_by_id(building_id: str, db: Session = Depends(get_db)):
    """Retrieves metadata for a specific building."""
    _seed_default_buildings_if_needed(db)
    building = db.query(Building).filter(Building.id == building_id).first()
    if not building:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Building with id '{building_id}' not found.",
        )
    return BuildingResponse.model_validate(building)


@router.post("", response_model=BuildingResponse, status_code=status.HTTP_201_CREATED, summary="Create a new building")
def create_building(payload: BuildingCreate, db: Session = Depends(get_db)):
    """Registers a new building profile in the database."""
    existing = db.query(Building).filter(Building.id == payload.id).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Building with id '{payload.id}' already exists.",
        )

    building = Building(
        id=payload.id,
        name=payload.name,
        building_type=payload.building_type,
        total_area_sqm=payload.total_area_sqm,
        location=payload.location,
        timezone=payload.timezone,
    )
    db.add(building)
    db.commit()
    db.refresh(building)
    return BuildingResponse.model_validate(building)


@router.get("/{building_id}/history", response_model=BuildingHistoryResponse, summary="Get historical energy consumption")
def get_building_history(
    building_id: str,
    limit: int = Query(default=168, ge=1, le=1000, description="Max readings to retrieve (default: 168h = 7 days)"),
    db: Session = Depends(get_db),
):
    """
    Retrieves sequential time-series meter telemetry for the requested building.
    Returns chronologically ordered points (oldest to newest) suitable for charts.
    """
    _seed_default_buildings_if_needed(db)
    building = db.query(Building).filter(Building.id == building_id).first()
    if not building:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Building with id '{building_id}' not found.",
        )

    _seed_initial_readings_if_needed(db, building_id=building_id)

    # Query newest records first up to limit, then reverse for chronological charting
    readings = (
        db.query(MeterReading)
        .filter(MeterReading.building_id == building_id)
        .order_by(MeterReading.timestamp.desc())
        .limit(limit)
        .all()
    )

    chronological_points = list(reversed(readings))

    return BuildingHistoryResponse(
        building_id=building_id,
        count=len(chronological_points),
        data=[HistoricalReadingPoint.model_validate(r) for r in chronological_points],
    )

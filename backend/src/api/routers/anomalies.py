"""
Anomaly Detection & Lifecycle Management API Router
Endpoints:
1. GET /api/v1/anomalies/events - Get list of detected anomaly incidents (synced with PostgreSQL)
2. PATCH /api/v1/anomalies/{anomaly_id}/status - Update incident lifecycle state (OPEN -> ACKNOWLEDGED -> RESOLVED)
"""

import asyncio
from datetime import datetime, timezone
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.api.schemas.anomalies import (
    AnomalyEvent,
    AnomalyStatusUpdateRequest,
    AnomalyStatusUpdateResponse,
)
from src.database import get_db
from src.data_pipeline.bdg2_loader import data_loader
from src.models.forecaster_xgboost import energy_forecaster
from src.models.anomaly_isolation_forest import anomaly_detector
from src.models.db_models import AnomalyEvent as DBAnomalyEvent, Building

logger = logging.getLogger("AnomaliesRouter")
router = APIRouter(prefix="/api/v1/anomalies", tags=["Anomaly Detection"])


def _ensure_default_building(db: Session, building_id: str = "office_tower_01") -> None:
    """Ensures a building record exists for foreign key integrity."""
    existing = db.query(Building).filter(Building.id == building_id).first()
    if not existing:
        b = Building(
            id=building_id,
            name="EcoTrack Headquarter Tower",
            building_type="Commercial Office",
            total_area_sqm=15200.0,
            location="Hanoi, Vietnam",
            timezone="Asia/Ho_Chi_Minh",
        )
        db.add(b)
        db.commit()


def _compute_and_sync_anomalies(db: Session) -> List[AnomalyEvent]:
    """
    Computes anomaly events via Isolation Forest pipeline and synchronizes
    persistent lifecycle states (OPEN, ACKNOWLEDGED, RESOLVED) from PostgreSQL.
    """
    _ensure_default_building(db)
    
    # 1. Fetch persistent states from DB
    db_events = {e.id: e for e in db.query(DBAnomalyEvent).all()}
    
    # 2. Run ML detection
    df = data_loader.get_or_create_data()
    df_fc = energy_forecaster.predict_horizon(df)
    df_anom = anomaly_detector.detect_anomalies(df_fc)
    
    anom_rows = df_anom[df_anom["is_anomaly"]].copy()
    events = []
    new_db_records = []
    
    for idx, row in anom_rows.iterrows():
        event_id = f"ANOM-{idx}"
        delta = round(float(row["residual"]), 1)
        cost_vnd = delta * 3100
        cost_usd = delta * 0.125
        
        # Check if already tracked in DB
        db_record = db_events.get(event_id)
        current_status = db_record.status if db_record else "OPEN"
        suggested_action = (
            db_record.suggested_action
            if (db_record and db_record.suggested_action)
            else (row.get("anomaly_reason") or "Inspect chiller plant schedule and sub-meter power draw.")
        )
        
        # If record is missing in DB, prepare to persist
        if not db_record:
            try:
                ts_str = str(row["timestamp"])
                dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except Exception:
                dt = datetime.now(timezone.utc)
                
            new_db_records.append(
                DBAnomalyEvent(
                    id=event_id,
                    building_id="office_tower_01",
                    timestamp=dt,
                    actual_reading=float(row["meter_reading_kwh"]),
                    anomaly_score=float(row["anomaly_score"]),
                    severity=str(row["severity"]).upper(),
                    suggested_action=suggested_action,
                    status="OPEN",
                )
            )
        
        events.append(AnomalyEvent(
            id=event_id,
            timestamp=str(row["timestamp"]),
            subsystem="Chiller & HVAC Plant",
            severity=str(row["severity"]),
            anomaly_score=float(row["anomaly_score"]),
            actual_kwh=float(row["meter_reading_kwh"]),
            predicted_kwh=float(row["predicted_kwh"]),
            delta_kwh=delta,
            outdoor_temp_c=float(row["outdoor_temperature_c"]),
            estimated_waste_vnd=round(cost_vnd, 0),
            estimated_waste_usd=round(cost_usd, 2),
            status=current_status,
            description=row.get("anomaly_reason") or "Abnormal load deviation exceeding baseline prediction",
            suggested_action=suggested_action,
        ))
    
    # Persist newly detected anomalies into DB for future lifecycle tracking
    if new_db_records:
        try:
            for rec in new_db_records:
                db.add(rec)
            db.commit()
            logger.info("Persisted %d newly identified anomaly events to database.", len(new_db_records))
        except Exception as exc:
            db.rollback()
            logger.warning("Could not bulk save new anomalies: %s", exc)
            
    return events[::-1]  # Newest first


@router.get("/events", response_model=List[AnomalyEvent], summary="Get list of detected anomaly incidents")
async def list_anomalies(db: Session = Depends(get_db)):
    """
    Returns detected anomaly incidents with their active lifecycle statuses
    (OPEN, ACKNOWLEDGED, RESOLVED) loaded from PostgreSQL.
    """
    events = await asyncio.to_thread(_compute_and_sync_anomalies, db)
    return events


@router.patch(
    "/{anomaly_id}/status",
    response_model=AnomalyStatusUpdateResponse,
    summary="Update incident lifecycle status",
)
def update_anomaly_status(
    anomaly_id: str,
    payload: AnomalyStatusUpdateRequest,
    db: Session = Depends(get_db),
):
    """
    Updates the lifecycle state of a specific anomaly event.
    Transitions: OPEN -> ACKNOWLEDGED -> RESOLVED.
    Persists the update directly into PostgreSQL database.
    """
    _ensure_default_building(db)
    
    # 1. Search for record in DB
    event_record = db.query(DBAnomalyEvent).filter(DBAnomalyEvent.id == anomaly_id).first()
    
    # 2. If not found, attempt to sync events from ML pipeline first
    if not event_record:
        _compute_and_sync_anomalies(db)
        event_record = db.query(DBAnomalyEvent).filter(DBAnomalyEvent.id == anomaly_id).first()
        
    if not event_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Anomaly incident with ID '{anomaly_id}' not found.",
        )
        
    previous_status = event_record.status
    event_record.status = payload.status
    
    # Append remediation note if provided
    if payload.note:
        note_entry = f" [{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')} Note: {payload.note}]"
        if event_record.suggested_action:
            event_record.suggested_action += note_entry
        else:
            event_record.suggested_action = note_entry

    db.commit()
    db.refresh(event_record)
    
    logger.info(
        "Anomaly '%s' transitioned status: %s -> %s",
        anomaly_id,
        previous_status,
        payload.status,
    )
    
    return AnomalyStatusUpdateResponse(
        id=anomaly_id,
        previous_status=previous_status,
        current_status=event_record.status,
        updated_at=datetime.now(timezone.utc),
        note=payload.note,
        message=f"Incident status successfully updated from '{previous_status}' to '{payload.status}'.",
    )

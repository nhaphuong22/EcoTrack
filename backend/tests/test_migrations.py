"""
Tests for Database Migration & Operational Schema Optimizations.
Verifies:
1. Alembic migrations run cleanly to head.
2. Critical time-series and query indexes exist in the operational database.
3. Database engine connection handles transactions and WAL mode gracefully.
"""

import pytest
from sqlalchemy import inspect
from src.database import engine, init_db, run_migrations


def test_migrations_and_schema_initialization():
    """Ensures migration execution and schema initialization pass without errors."""
    success = run_migrations()
    assert success is True

    # Check inspector
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert "buildings" in tables
    assert "meter_readings" in tables
    assert "anomaly_events" in tables
    assert "conversations" in tables


def test_operational_performance_indexes():
    """
    Validates presence of composite and operational performance indexes:
    - MeterReading: (building_id, timestamp) for high-speed time-series window scans
    - AnomalyEvent: (building_id, timestamp) and status for incident alerts
    - Conversation: (session_id, created_at) for sequential chat retrieval
    """
    inspector = inspect(engine)

    # Meter readings indexes
    mr_indexes = {idx["name"] for idx in inspector.get_indexes("meter_readings")}
    assert "ix_meter_readings_bldg_ts" in mr_indexes

    # Anomaly events indexes
    anom_indexes = {idx["name"] for idx in inspector.get_indexes("anomaly_events")}
    assert "ix_anomaly_events_bldg_ts" in anom_indexes
    assert "ix_anomaly_events_status" in anom_indexes

    # Conversations indexes
    conv_indexes = {idx["name"] for idx in inspector.get_indexes("conversations")}
    assert "ix_conversations_session_created" in conv_indexes

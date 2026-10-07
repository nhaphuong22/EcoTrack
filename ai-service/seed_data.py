"""
Database Seeding Script for EcoTrack (Development & Production Setup).
Initializes database tables, creates default monitored buildings,
and seeds initial clean baseline telemetry readings from BDG2 / ASHRAE dataset.

Usage:
    python seed_data.py
    # or from repo root:
    python backend/seed_data.py
"""

import os
import sys
from pathlib import Path
import logging

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("EcoTrackSeeder")

from src.database import SessionLocal, init_db
from src.api.routers.buildings import (
    _seed_default_buildings_if_needed,
    _seed_initial_readings_if_needed,
)
from src.models.db_models import Building, MeterReading


def seed_database(sample_hours: int = 168) -> None:
    """
    Executes end-to-end database initialization and clean sample data seeding.
    """
    logger.info("Initializing database schema...")
    init_db()

    db = SessionLocal()
    try:
        building_count_before = db.query(Building).count()
        reading_count_before = db.query(MeterReading).count()

        logger.info(
            "Current DB status: %d buildings, %d meter readings.",
            building_count_before,
            reading_count_before,
        )

        logger.info("Seeding default buildings...")
        _seed_default_buildings_if_needed(db)

        buildings = db.query(Building).all()
        logger.info("Total buildings in database: %d", len(buildings))
        for b in buildings:
            area = b.total_area_sqm or 0.0
            logger.info(" - [%s] %s (%s, %.0f m²)", b.id, b.name, b.building_type, area)
            _seed_initial_readings_if_needed(db, building_id=b.id, sample_hours=sample_hours)

        total_readings = db.query(MeterReading).count()
        logger.info("Database seeding completed successfully! Total readings: %d.", total_readings)

    except Exception as exc:
        logger.error("Error while seeding database: %s", exc, exc_info=True)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    print("=" * 70)
    print("🌱 ECOTRACK DATABASE SEEDER (SAMPLE TELEMETRY)")
    print("=" * 70)
    seed_database()
    print("=" * 70)
    print("✅ Hoàn tất nạp dữ liệu mẫu sạch!")
    print("=" * 70)

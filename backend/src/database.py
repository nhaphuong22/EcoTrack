"""
Database Configuration & Engine Setup for EcoTrack
Connects to PostgreSQL (Docker) with automatic SQLite fallback for local test/dev.
Provides the SQLAlchemy Base, SessionLocal factory, and FastAPI get_db dependency.
"""

import logging
import os
from pathlib import Path
from typing import Generator
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

load_dotenv()
logger = logging.getLogger("EcoTrackDatabase")

# Target database URL: PostgreSQL in docker/production, or configured in .env
DEFAULT_POSTGRES_URL = "postgresql://ecotrack:ecotrack_secret@localhost:5432/ecotrack"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_POSTGRES_URL)

# Fallback SQLite path if PostgreSQL is unreachable during quick local tests
FALLBACK_SQLITE_URL = f"sqlite:///{Path(__file__).resolve().parents[1]}/ecotrack_local.db"


def _build_engine():
    """
    Attempts to initialize the database engine.
    If PostgreSQL is unavailable in local testing without docker,
    gracefully falls back to local SQLite to ensure the backend remains operational.
    """
    target_url = DATABASE_URL
    # Normalize postgres:// scheme if provided by some cloud providers
    if target_url.startswith("postgres://"):
        target_url = target_url.replace("postgres://", "postgresql://", 1)

    try:
        if target_url.startswith("sqlite"):
            eng = create_engine(target_url, connect_args={"check_same_thread": False})
        else:
            eng = create_engine(
                target_url,
                pool_pre_ping=True,
                pool_size=10,
                max_overflow=20,
                connect_args={"connect_timeout": 3},
            )
            # Test quick connection with a low timeout to fail fast if DB is down locally
            with eng.connect():
                pass
        logger.info("Successfully connected to database: %s", target_url.split("@")[-1] if "@" in target_url else target_url)
        return eng
    except Exception as exc:
        logger.warning(
            "Primary database connection failed (%s). Falling back to local SQLite: %s",
            exc,
            FALLBACK_SQLITE_URL,
        )
        return create_engine(
            FALLBACK_SQLITE_URL,
            connect_args={"check_same_thread": False},
        )


engine = _build_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that provides a transactional database session per request.
    Automatically closes session after completion.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Creates all database tables defined by SQLAlchemy models."""
    try:
        # Import models so they are registered on Base.metadata
        from src.models import db_models  # noqa: F401
        Base.metadata.create_all(bind=engine)
        logger.info("Database schema initialized successfully.")
    except Exception as exc:
        logger.error("Failed to initialize database schema: %s", exc)

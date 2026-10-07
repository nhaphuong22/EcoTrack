"""
Database Configuration, Engine Setup & Migration Management for EcoTrack
Connects to PostgreSQL (Docker) with automatic SQLite fallback for local test/dev.
Optimizes operational performance via connection pooling, SQLite WAL mode, and Alembic migrations.
Provides the SQLAlchemy Base, SessionLocal factory, and FastAPI get_db dependency.
"""

import logging
import os
from pathlib import Path
from typing import Generator
from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

load_dotenv()
logger = logging.getLogger("EcoTrackDatabase")

# Target database URL: PostgreSQL in docker/production, or configured in .env
DEFAULT_POSTGRES_URL = "postgresql://ecotrack:ecotrack_secret@localhost:5432/ecotrack"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_POSTGRES_URL)

# Fallback SQLite path if PostgreSQL is unreachable during quick local tests
FALLBACK_SQLITE_URL = f"sqlite:///{Path(__file__).resolve().parents[1]}/ecotrack_local.db"


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """
    Operational Data Optimization for SQLite:
    - journal_mode=WAL: Allows non-blocking concurrent reads while appending telemetry
    - synchronous=NORMAL: Maximizes disk I/O write throughput without sacrificing durability
    - foreign_keys=ON: Enforces relational constraints & cascading deletes
    """
    if type(dbapi_connection).__module__ == "sqlite3":
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def _build_engine():
    """
    Attempts to initialize the database engine.
    If PostgreSQL is unavailable in local testing without docker,
    gracefully falls back to local SQLite to ensure the backend remains operational.
    """
    target_url = DATABASE_URL
    # Normalize postgres:// and postgresql:// schemes to use psycopg2 driver
    if target_url.startswith("postgres://"):
        target_url = target_url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif target_url.startswith("postgresql://") and not target_url.startswith("postgresql+"):
        target_url = target_url.replace("postgresql://", "postgresql+psycopg2://", 1)

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


def run_migrations() -> bool:
    """
    Applies Alembic migrations up to head programmatically.
    Returns True if migrations executed successfully, False otherwise.
    """
    try:
        from alembic.config import Config
        from alembic import command

        backend_dir = Path(__file__).resolve().parents[1]
        alembic_ini_path = backend_dir / "alembic.ini"
        if alembic_ini_path.exists():
            alembic_cfg = Config(str(alembic_ini_path))
            alembic_cfg.set_main_option("script_location", str(backend_dir / "alembic"))
            command.upgrade(alembic_cfg, "head")
            logger.info("Alembic database migrations applied successfully to head.")
            return True
    except Exception as exc:
        logger.warning("Alembic migration execution skipped or encountered notice: %s", exc)
    return False


def init_db() -> None:
    """
    Initializes database schema using Alembic migrations first.
    Falls back to Base.metadata.create_all if needed.
    """
    try:
        from src.models import db_models  # noqa: F401
        migrated = run_migrations()
        if not migrated:
            Base.metadata.create_all(bind=engine)
            logger.info("Database schema initialized via create_all fallback.")
    except Exception as exc:
        logger.error("Failed to initialize database schema: %s", exc)

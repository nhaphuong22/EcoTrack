"""
SQLAlchemy ORM Models for EcoTrack
Defines the core entities:
1. Building - Metadata and properties of managed buildings
2. MeterReading - Hourly energy telemetry and weather indicators
3. AnomalyEvent - Detected energy spikes and anomalies with severity
4. Conversation - Copilot LLM chat history and user interactions
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from src.database import Base


class Building(Base):
    """Represents a monitored facility or commercial office building."""

    __tablename__ = "buildings"

    id = Column(String(50), primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    building_type = Column(String(50), default="Office", nullable=False)
    total_area_sqm = Column(Float, nullable=True)
    location = Column(String(100), nullable=True)
    timezone = Column(String(50), default="UTC", nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    meter_readings = relationship(
        "MeterReading",
        back_populates="building",
        cascade="all, delete-orphan",
        order_by="MeterReading.timestamp.desc()",
    )
    anomaly_events = relationship(
        "AnomalyEvent",
        back_populates="building",
        cascade="all, delete-orphan",
        order_by="AnomalyEvent.timestamp.desc()",
    )
    conversations = relationship(
        "Conversation",
        back_populates="building",
        cascade="all, delete-orphan",
        order_by="Conversation.created_at.asc()",
    )

    def __repr__(self) -> str:
        return f"<Building(id='{self.id}', name='{self.name}', type='{self.building_type}')>"


class MeterReading(Base):
    """Stores sequential time-series energy consumption and ambient weather telemetry."""

    __tablename__ = "meter_readings"
    __table_args__ = (
        Index("ix_meter_readings_bldg_ts", "building_id", "timestamp"),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    building_id = Column(
        String(50),
        ForeignKey("buildings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    meter_reading_kwh = Column(Float, nullable=False)
    outdoor_temperature_c = Column(Float, nullable=True)
    relative_humidity_pct = Column(Float, nullable=True)
    recorded_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationship
    building = relationship("Building", back_populates="meter_readings")

    def __repr__(self) -> str:
        return (
            f"<MeterReading(id={self.id}, building_id='{self.building_id}', "
            f"timestamp='{self.timestamp}', kwh={self.meter_reading_kwh})>"
        )


class AnomalyEvent(Base):
    """Stores detected abnormal energy consumption incidents flagged by Isolation Forest."""

    __tablename__ = "anomaly_events"
    __table_args__ = (
        Index("ix_anomaly_events_bldg_ts", "building_id", "timestamp"),
        Index("ix_anomaly_events_status", "status"),
    )

    id = Column(String(50), primary_key=True, index=True)  # e.g. ANOM-4B2E81FA
    building_id = Column(
        String(50),
        ForeignKey("buildings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    actual_reading = Column(Float, nullable=False)
    anomaly_score = Column(Float, nullable=False)
    severity = Column(String(20), nullable=False)  # LOW, MEDIUM, CRITICAL
    suggested_action = Column(Text, nullable=True)
    status = Column(String(20), default="OPEN", nullable=False)  # OPEN, RESOLVED, IGNORED
    detected_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationship
    building = relationship("Building", back_populates="anomaly_events")

    def __repr__(self) -> str:
        return (
            f"<AnomalyEvent(id='{self.id}', building_id='{self.building_id}', "
            f"severity='{self.severity}', reading={self.actual_reading})>"
        )


class Conversation(Base):
    """Stores chat conversations between building operators and the AI Copilot."""

    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversations_session_created", "session_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    building_id = Column(
        String(50),
        ForeignKey("buildings.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    session_id = Column(String(50), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # 'user', 'assistant', 'system'
    message = Column(Text, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationship
    building = relationship("Building", back_populates="conversations")

    def __repr__(self) -> str:
        return f"<Conversation(id={self.id}, session_id='{self.session_id}', role='{self.role}')>"

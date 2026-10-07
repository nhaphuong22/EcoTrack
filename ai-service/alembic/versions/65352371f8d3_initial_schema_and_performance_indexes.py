"""initial_schema_and_performance_indexes

Revision ID: 65352371f8d3
Revises: 
Create Date: 2026-10-06 09:03:01.687096

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '65352371f8d3'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # 1. Create tables if starting with a fresh database
    if "buildings" not in existing_tables:
        op.create_table(
            "buildings",
            sa.Column("id", sa.String(length=50), primary_key=True),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("building_type", sa.String(length=50), nullable=False, server_default="Office"),
            sa.Column("total_area_sqm", sa.Float(), nullable=True),
            sa.Column("location", sa.String(length=100), nullable=True),
            sa.Column("timezone", sa.String(length=50), nullable=False, server_default="UTC"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_buildings_id", "buildings", ["id"], unique=False)

    if "meter_readings" not in existing_tables:
        op.create_table(
            "meter_readings",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("building_id", sa.String(length=50), sa.ForeignKey("buildings.id", ondelete="CASCADE"), nullable=False),
            sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
            sa.Column("meter_reading_kwh", sa.Float(), nullable=False),
            sa.Column("outdoor_temperature_c", sa.Float(), nullable=True),
            sa.Column("relative_humidity_pct", sa.Float(), nullable=True),
            sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_meter_readings_id", "meter_readings", ["id"], unique=False)
        op.create_index("ix_meter_readings_building_id", "meter_readings", ["building_id"], unique=False)
        op.create_index("ix_meter_readings_timestamp", "meter_readings", ["timestamp"], unique=False)

    if "anomaly_events" not in existing_tables:
        op.create_table(
            "anomaly_events",
            sa.Column("id", sa.String(length=50), primary_key=True),
            sa.Column("building_id", sa.String(length=50), sa.ForeignKey("buildings.id", ondelete="CASCADE"), nullable=False),
            sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
            sa.Column("actual_reading", sa.Float(), nullable=False),
            sa.Column("anomaly_score", sa.Float(), nullable=False),
            sa.Column("severity", sa.String(length=20), nullable=False),
            sa.Column("suggested_action", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="OPEN"),
            sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_anomaly_events_id", "anomaly_events", ["id"], unique=False)
        op.create_index("ix_anomaly_events_building_id", "anomaly_events", ["building_id"], unique=False)
        op.create_index("ix_anomaly_events_timestamp", "anomaly_events", ["timestamp"], unique=False)

    if "conversations" not in existing_tables:
        op.create_table(
            "conversations",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("building_id", sa.String(length=50), sa.ForeignKey("buildings.id", ondelete="CASCADE"), nullable=True),
            sa.Column("session_id", sa.String(length=50), nullable=False),
            sa.Column("role", sa.String(length=20), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_conversations_id", "conversations", ["id"], unique=False)
        op.create_index("ix_conversations_building_id", "conversations", ["building_id"], unique=False)
        op.create_index("ix_conversations_session_id", "conversations", ["session_id"], unique=False)

    # 2. Add Composite Performance Indexes for High-Throughput Telemetry & Analytics
    inspector = sa.inspect(bind)
    
    # Meter reading composite index (building_id + timestamp)
    existing_mr_indexes = {idx["name"] for idx in inspector.get_indexes("meter_readings")}
    if "ix_meter_readings_bldg_ts" not in existing_mr_indexes:
        with op.batch_alter_table("meter_readings", schema=None) as batch_op:
            batch_op.create_index("ix_meter_readings_bldg_ts", ["building_id", "timestamp"], unique=False)

    # Anomaly composite index (building_id + timestamp) & status index
    existing_anom_indexes = {idx["name"] for idx in inspector.get_indexes("anomaly_events")}
    if "ix_anomaly_events_bldg_ts" not in existing_anom_indexes:
        with op.batch_alter_table("anomaly_events", schema=None) as batch_op:
            batch_op.create_index("ix_anomaly_events_bldg_ts", ["building_id", "timestamp"], unique=False)
    if "ix_anomaly_events_status" not in existing_anom_indexes:
        with op.batch_alter_table("anomaly_events", schema=None) as batch_op:
            batch_op.create_index("ix_anomaly_events_status", ["status"], unique=False)

    # Conversations composite index (session_id + created_at)
    existing_conv_indexes = {idx["name"] for idx in inspector.get_indexes("conversations")}
    if "ix_conversations_session_created" not in existing_conv_indexes:
        with op.batch_alter_table("conversations", schema=None) as batch_op:
            batch_op.create_index("ix_conversations_session_created", ["session_id", "created_at"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "conversations" in inspector.get_table_names():
        with op.batch_alter_table("conversations", schema=None) as batch_op:
            batch_op.drop_index("ix_conversations_session_created")

    if "anomaly_events" in inspector.get_table_names():
        with op.batch_alter_table("anomaly_events", schema=None) as batch_op:
            batch_op.drop_index("ix_anomaly_events_status")
            batch_op.drop_index("ix_anomaly_events_bldg_ts")

    if "meter_readings" in inspector.get_table_names():
        with op.batch_alter_table("meter_readings", schema=None) as batch_op:
            batch_op.drop_index("ix_meter_readings_bldg_ts")

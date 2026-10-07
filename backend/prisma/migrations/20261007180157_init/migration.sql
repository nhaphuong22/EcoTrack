-- CreateTable
CREATE TABLE "buildings" (
    "id" VARCHAR(50) NOT NULL,
    "name" VARCHAR(100) NOT NULL,
    "building_type" VARCHAR(50) NOT NULL DEFAULT 'Office',
    "total_area_sqm" DOUBLE PRECISION,
    "location" VARCHAR(100),
    "timezone" VARCHAR(50) NOT NULL DEFAULT 'UTC',
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "buildings_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "meter_readings" (
    "id" SERIAL NOT NULL,
    "building_id" VARCHAR(50) NOT NULL,
    "timestamp" TIMESTAMPTZ NOT NULL,
    "meter_reading_kwh" DOUBLE PRECISION NOT NULL,
    "outdoor_temperature_c" DOUBLE PRECISION,
    "relative_humidity_pct" DOUBLE PRECISION,
    "recorded_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "meter_readings_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "anomaly_events" (
    "id" VARCHAR(50) NOT NULL,
    "building_id" VARCHAR(50) NOT NULL,
    "timestamp" TIMESTAMPTZ NOT NULL,
    "actual_reading" DOUBLE PRECISION NOT NULL,
    "anomaly_score" DOUBLE PRECISION NOT NULL,
    "severity" VARCHAR(20) NOT NULL,
    "suggested_action" TEXT,
    "status" VARCHAR(20) NOT NULL DEFAULT 'OPEN',
    "detected_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "anomaly_events_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "conversations" (
    "id" SERIAL NOT NULL,
    "building_id" VARCHAR(50),
    "session_id" VARCHAR(50) NOT NULL,
    "role" VARCHAR(20) NOT NULL,
    "message" TEXT NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "conversations_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "ix_meter_readings_bldg_ts" ON "meter_readings"("building_id", "timestamp");

-- CreateIndex
CREATE INDEX "ix_meter_readings_building_id" ON "meter_readings"("building_id");

-- CreateIndex
CREATE INDEX "ix_meter_readings_timestamp" ON "meter_readings"("timestamp");

-- CreateIndex
CREATE INDEX "ix_anomaly_events_bldg_ts" ON "anomaly_events"("building_id", "timestamp");

-- CreateIndex
CREATE INDEX "ix_anomaly_events_status" ON "anomaly_events"("status");

-- CreateIndex
CREATE INDEX "ix_anomaly_events_building_id" ON "anomaly_events"("building_id");

-- CreateIndex
CREATE INDEX "ix_anomaly_events_timestamp" ON "anomaly_events"("timestamp");

-- CreateIndex
CREATE INDEX "ix_conversations_session_created" ON "conversations"("session_id", "created_at");

-- CreateIndex
CREATE INDEX "ix_conversations_session_id" ON "conversations"("session_id");

-- CreateIndex
CREATE INDEX "ix_conversations_building_id" ON "conversations"("building_id");

-- AddForeignKey
ALTER TABLE "meter_readings" ADD CONSTRAINT "meter_readings_building_id_fkey" FOREIGN KEY ("building_id") REFERENCES "buildings"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "anomaly_events" ADD CONSTRAINT "anomaly_events_building_id_fkey" FOREIGN KEY ("building_id") REFERENCES "buildings"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "conversations" ADD CONSTRAINT "conversations_building_id_fkey" FOREIGN KEY ("building_id") REFERENCES "buildings"("id") ON DELETE CASCADE ON UPDATE CASCADE;

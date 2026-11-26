-- AlterTable
ALTER TABLE "meter_readings" ADD COLUMN IF NOT EXISTS "zone_id" VARCHAR(50);

-- CreateTable
CREATE TABLE IF NOT EXISTS "zones" (
    "id" VARCHAR(50) NOT NULL,
    "building_id" VARCHAR(50) NOT NULL,
    "floor" INTEGER NOT NULL DEFAULT 1,
    "name" VARCHAR(100) NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "zones_pkey" PRIMARY KEY ("id")
);

-- Deduplicate existing meter_readings keeping lowest id before adding unique constraints
DELETE FROM "meter_readings" a USING "meter_readings" b
WHERE a.id > b.id
  AND a.building_id = b.building_id
  AND a.timestamp = b.timestamp
  AND (a.zone_id = b.zone_id OR (a.zone_id IS NULL AND b.zone_id IS NULL));

-- CreateIndex
CREATE INDEX IF NOT EXISTS "ix_zones_building_id" ON "zones"("building_id");

-- CreateIndex
CREATE INDEX IF NOT EXISTS "ix_meter_readings_zone_id" ON "meter_readings"("zone_id");

-- CreateIndex
CREATE UNIQUE INDEX IF NOT EXISTS "uq_meter_readings_bldg_zone_ts" ON "meter_readings"("building_id", "zone_id", "timestamp");

-- Partial unique index for zoneless readings where zone_id IS NULL
CREATE UNIQUE INDEX IF NOT EXISTS "uq_meter_readings_bldg_ts_null_zone" ON "meter_readings"("building_id", "timestamp") WHERE "zone_id" IS NULL;

-- AddForeignKey
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'zones_building_id_fkey'
    ) THEN
        ALTER TABLE "zones" ADD CONSTRAINT "zones_building_id_fkey" FOREIGN KEY ("building_id") REFERENCES "buildings"("id") ON DELETE CASCADE ON UPDATE CASCADE;
    END IF;
END $$;

-- AddForeignKey
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'meter_readings_zone_id_fkey'
    ) THEN
        ALTER TABLE "meter_readings" ADD CONSTRAINT "meter_readings_zone_id_fkey" FOREIGN KEY ("zone_id") REFERENCES "zones"("id") ON DELETE CASCADE ON UPDATE CASCADE;
    END IF;
END $$;

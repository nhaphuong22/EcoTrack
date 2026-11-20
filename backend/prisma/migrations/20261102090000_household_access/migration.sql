-- AlterTable
ALTER TABLE "zones" ADD COLUMN     "unit_id" UUID;

-- AlterTable
ALTER TABLE "meter_readings" ADD COLUMN     "meter_id" VARCHAR(50);

-- AlterTable
ALTER TABLE "anomaly_events" ADD COLUMN     "meter_id" VARCHAR(50);

-- AlterTable
ALTER TABLE "conversations" ADD COLUMN     "chat_id" UUID;

-- CreateTable
CREATE TABLE "users" (
    "id" UUID NOT NULL,
    "email" VARCHAR(254) NOT NULL,
    "name" VARCHAR(100) NOT NULL,
    "password_hash" TEXT NOT NULL,
    "active" BOOLEAN NOT NULL DEFAULT true,
    "is_platform_admin" BOOLEAN NOT NULL DEFAULT false,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "users_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "auth_sessions" (
    "id" UUID NOT NULL,
    "user_id" UUID NOT NULL,
    "token_hash" VARCHAR(64) NOT NULL,
    "expires_at" TIMESTAMPTZ NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "auth_sessions_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "units" (
    "id" UUID NOT NULL,
    "building_id" VARCHAR(50) NOT NULL,
    "code" VARCHAR(30) NOT NULL,
    "floor" INTEGER NOT NULL DEFAULT 1,
    "active" BOOLEAN NOT NULL DEFAULT true,

    CONSTRAINT "units_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "households" (
    "id" UUID NOT NULL,
    "unit_id" UUID NOT NULL,
    "name" VARCHAR(100) NOT NULL,
    "starts_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "ends_at" TIMESTAMPTZ,

    CONSTRAINT "households_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "household_members" (
    "id" UUID NOT NULL,
    "household_id" UUID NOT NULL,
    "user_id" UUID NOT NULL,
    "role" VARCHAR(20) NOT NULL DEFAULT 'MEMBER',
    "starts_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "ends_at" TIMESTAMPTZ,

    CONSTRAINT "household_members_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "building_staff" (
    "id" UUID NOT NULL,
    "building_id" VARCHAR(50) NOT NULL,
    "user_id" UUID NOT NULL,
    "role" VARCHAR(20) NOT NULL DEFAULT 'MANAGER',

    CONSTRAINT "building_staff_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "meters" (
    "id" VARCHAR(50) NOT NULL,
    "building_id" VARCHAR(50) NOT NULL,
    "unit_id" UUID,
    "zone_id" VARCHAR(50),
    "name" VARCHAR(100) NOT NULL,
    "scope" VARCHAR(20) NOT NULL,
    "interval_seconds" INTEGER NOT NULL DEFAULT 3600,

    CONSTRAINT "meters_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "invitations" (
    "id" UUID NOT NULL,
    "household_id" UUID NOT NULL,
    "email" VARCHAR(254) NOT NULL,
    "token_hash" VARCHAR(64) NOT NULL,
    "role" VARCHAR(20) NOT NULL DEFAULT 'MEMBER',
    "created_by" UUID NOT NULL,
    "expires_at" TIMESTAMPTZ NOT NULL,
    "accepted_at" TIMESTAMPTZ,

    CONSTRAINT "invitations_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "chat_sessions" (
    "id" UUID NOT NULL,
    "user_id" UUID NOT NULL,
    "building_id" VARCHAR(50) NOT NULL,
    "household_id" UUID,
    "scope" VARCHAR(20) NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "chat_sessions_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "users_email_key" ON "users"("email");

-- CreateIndex
CREATE UNIQUE INDEX "auth_sessions_token_hash_key" ON "auth_sessions"("token_hash");

-- CreateIndex
CREATE INDEX "auth_sessions_user_id_idx" ON "auth_sessions"("user_id");

-- CreateIndex
CREATE UNIQUE INDEX "units_building_id_code_key" ON "units"("building_id", "code");

-- CreateIndex
CREATE INDEX "households_unit_id_idx" ON "households"("unit_id");

-- CreateIndex
CREATE INDEX "household_members_user_id_idx" ON "household_members"("user_id");

-- CreateIndex
CREATE UNIQUE INDEX "household_members_household_id_user_id_key" ON "household_members"("household_id", "user_id");

-- CreateIndex
CREATE INDEX "building_staff_user_id_idx" ON "building_staff"("user_id");

-- CreateIndex
CREATE UNIQUE INDEX "building_staff_building_id_user_id_key" ON "building_staff"("building_id", "user_id");

-- CreateIndex
CREATE UNIQUE INDEX "meters_zone_id_key" ON "meters"("zone_id");

-- CreateIndex
CREATE INDEX "meters_building_id_scope_idx" ON "meters"("building_id", "scope");

-- CreateIndex
CREATE INDEX "meters_unit_id_idx" ON "meters"("unit_id");

-- CreateIndex
CREATE UNIQUE INDEX "invitations_token_hash_key" ON "invitations"("token_hash");

-- CreateIndex
CREATE INDEX "invitations_household_id_idx" ON "invitations"("household_id");

-- CreateIndex
CREATE INDEX "chat_sessions_user_id_created_at_idx" ON "chat_sessions"("user_id", "created_at");

-- CreateIndex
CREATE UNIQUE INDEX "meter_readings_meter_id_timestamp_key" ON "meter_readings"("meter_id", "timestamp");

-- AddForeignKey
ALTER TABLE "zones" ADD CONSTRAINT "zones_unit_id_fkey" FOREIGN KEY ("unit_id") REFERENCES "units"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "meter_readings" ADD CONSTRAINT "meter_readings_meter_id_fkey" FOREIGN KEY ("meter_id") REFERENCES "meters"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "anomaly_events" ADD CONSTRAINT "anomaly_events_meter_id_fkey" FOREIGN KEY ("meter_id") REFERENCES "meters"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "conversations" ADD CONSTRAINT "conversations_chat_id_fkey" FOREIGN KEY ("chat_id") REFERENCES "chat_sessions"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "auth_sessions" ADD CONSTRAINT "auth_sessions_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "units" ADD CONSTRAINT "units_building_id_fkey" FOREIGN KEY ("building_id") REFERENCES "buildings"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "households" ADD CONSTRAINT "households_unit_id_fkey" FOREIGN KEY ("unit_id") REFERENCES "units"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "household_members" ADD CONSTRAINT "household_members_household_id_fkey" FOREIGN KEY ("household_id") REFERENCES "households"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "household_members" ADD CONSTRAINT "household_members_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "building_staff" ADD CONSTRAINT "building_staff_building_id_fkey" FOREIGN KEY ("building_id") REFERENCES "buildings"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "building_staff" ADD CONSTRAINT "building_staff_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "meters" ADD CONSTRAINT "meters_building_id_fkey" FOREIGN KEY ("building_id") REFERENCES "buildings"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "meters" ADD CONSTRAINT "meters_unit_id_fkey" FOREIGN KEY ("unit_id") REFERENCES "units"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "meters" ADD CONSTRAINT "meters_zone_id_fkey" FOREIGN KEY ("zone_id") REFERENCES "zones"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "invitations" ADD CONSTRAINT "invitations_household_id_fkey" FOREIGN KEY ("household_id") REFERENCES "households"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "invitations" ADD CONSTRAINT "invitations_created_by_fkey" FOREIGN KEY ("created_by") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "chat_sessions" ADD CONSTRAINT "chat_sessions_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- Preserve the demo data without guessing which rooms are apartments.
INSERT INTO "meters" (id, building_id, name, scope)
SELECT 'meter-' || md5(id || ':total'), id, 'Building total', 'BUILDING_TOTAL' FROM buildings;
INSERT INTO "meters" (id, building_id, zone_id, name, scope)
SELECT 'meter-' || md5(building_id || ':' || id), building_id, id, name, 'UNASSIGNED' FROM zones;
UPDATE meter_readings SET meter_id = 'meter-' || md5(building_id || ':' || COALESCE(zone_id, 'total'));

CREATE UNIQUE INDEX households_one_open_occupancy ON households(unit_id) WHERE ends_at IS NULL;
ALTER TABLE households ADD CONSTRAINT households_valid_dates CHECK (ends_at IS NULL OR ends_at >= starts_at);
ALTER TABLE household_members ADD CONSTRAINT household_members_valid_dates CHECK (ends_at IS NULL OR ends_at >= starts_at);
ALTER TABLE household_members ADD CONSTRAINT household_members_role CHECK (role IN ('OWNER', 'MEMBER'));
ALTER TABLE building_staff ADD CONSTRAINT building_staff_role CHECK (role = 'MANAGER');
ALTER TABLE invitations ADD CONSTRAINT invitations_role CHECK (role IN ('OWNER', 'MEMBER'));
ALTER TABLE meters ADD CONSTRAINT meters_scope CHECK (
  (scope = 'UNIT' AND unit_id IS NOT NULL) OR
  (scope IN ('BUILDING_TOTAL', 'COMMON', 'UNASSIGNED') AND unit_id IS NULL)
);
ALTER TABLE meters ADD CONSTRAINT meters_positive_interval CHECK (interval_seconds > 0);
ALTER TABLE chat_sessions ADD CONSTRAINT chat_sessions_scope CHECK (
  (scope = 'household' AND household_id IS NOT NULL) OR (scope IN ('building', 'common') AND household_id IS NULL)
);
ALTER TABLE chat_sessions ADD CONSTRAINT chat_sessions_building_fk FOREIGN KEY (building_id) REFERENCES buildings(id) ON DELETE RESTRICT;
ALTER TABLE chat_sessions ADD CONSTRAINT chat_sessions_household_fk FOREIGN KEY (household_id) REFERENCES households(id) ON DELETE RESTRICT;

-- Enforce the same building/unit boundary even for writes outside Express.
CREATE FUNCTION validate_meter_ownership() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.unit_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM units WHERE id = NEW.unit_id AND building_id = NEW.building_id) THEN
    RAISE EXCEPTION 'Meter unit belongs to another building';
  END IF;
  IF NEW.zone_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM zones WHERE id = NEW.zone_id AND building_id = NEW.building_id AND unit_id IS NOT DISTINCT FROM NEW.unit_id) THEN
    RAISE EXCEPTION 'Meter zone ownership mismatch';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER meters_validate_ownership BEFORE INSERT OR UPDATE ON meters FOR EACH ROW EXECUTE FUNCTION validate_meter_ownership();

CREATE FUNCTION validate_reading_meter() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.meter_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM meters WHERE id = NEW.meter_id AND building_id = NEW.building_id AND zone_id IS NOT DISTINCT FROM NEW.zone_id
  ) THEN RAISE EXCEPTION 'Reading meter ownership mismatch'; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER meter_readings_validate_ownership BEFORE INSERT OR UPDATE ON meter_readings FOR EACH ROW EXECUTE FUNCTION validate_reading_meter();

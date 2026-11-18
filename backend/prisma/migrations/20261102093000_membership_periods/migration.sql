-- Retain prior access periods when a former member is explicitly invited again.
DROP INDEX "household_members_household_id_user_id_key";
CREATE INDEX "household_members_household_id_user_id_idx" ON household_members(household_id, user_id);
CREATE UNIQUE INDEX household_members_one_active_period ON household_members(household_id, user_id) WHERE ends_at IS NULL;

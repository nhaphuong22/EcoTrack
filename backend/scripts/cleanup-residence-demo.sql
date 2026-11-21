-- Removes the 8 demo apartments (units 101-108, zones r1-r8) that an earlier seed created in residence_01, but KEEPS
-- everything a manager added by hand (e.g. household "alo"): the building, any unit that still has a non-seed
-- household, and that unit's zone/meter. Seed households are only deleted when they have no members or invitations.
-- Ends in ROLLBACK as a dry run: change the last line to COMMIT once the counts look right.
BEGIN;

DELETE FROM households h
 USING units u
 WHERE h.unit_id = u.id AND u.building_id = 'residence_01'
   AND h.name = 'Hộ ' || u.code AND u.code IN ('101','102','103','104','105','106','107','108')
   AND NOT EXISTS (SELECT 1 FROM household_members m WHERE m.household_id = h.id)
   AND NOT EXISTS (SELECT 1 FROM invitations i WHERE i.household_id = h.id);

-- Seed units that no longer have any household are the ones to remove.
CREATE TEMP TABLE gone_units ON COMMIT DROP AS
  SELECT id FROM units u
   WHERE u.building_id = 'residence_01' AND u.code IN ('101','102','103','104','105','106','107','108')
     AND NOT EXISTS (SELECT 1 FROM households h WHERE h.unit_id = u.id);

DELETE FROM anomaly_events WHERE meter_id IN (SELECT id FROM meters WHERE unit_id IN (SELECT id FROM gone_units));
DELETE FROM meter_readings WHERE meter_id IN (SELECT id FROM meters WHERE unit_id IN (SELECT id FROM gone_units));
DELETE FROM meters WHERE unit_id IN (SELECT id FROM gone_units);
DELETE FROM zones  WHERE unit_id IN (SELECT id FROM gone_units);
DELETE FROM units  WHERE id IN (SELECT id FROM gone_units);

SELECT u.code AS unit_left, h.name AS household, z.id AS zone
  FROM units u LEFT JOIN households h ON h.unit_id = u.id LEFT JOIN zones z ON z.unit_id = u.id
 WHERE u.building_id = 'residence_01' ORDER BY u.code;
ROLLBACK;

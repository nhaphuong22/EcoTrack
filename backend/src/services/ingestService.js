const prisma = require('../db');

// ponytail: single-batch createMany with skipDuplicates; partition or stream if ingestion volume exceeds 10k/s
async function ingestReadings(readings) {
  if (!Array.isArray(readings) || readings.length === 0) {
    return { stored: 0 };
  }

  // 1. Validate building existence
  const buildingIds = [...new Set(readings.map((r) => r.building_id))];
  const existingBuildings = await prisma.building.findMany({
    where: { id: { in: buildingIds } },
    select: { id: true },
  });
  const existingBuildingSet = new Set(existingBuildings.map((b) => b.id));

  for (const bId of buildingIds) {
    if (!existingBuildingSet.has(bId)) {
      const err = new Error(`Building with id '${bId}' not found.`);
      err.status = 422;
      throw err;
    }
  }

  // 2. Validate zone existence if zone_id provided
  const zoneIds = [...new Set(readings.map((r) => r.zone_id).filter(Boolean))];
  if (zoneIds.length > 0) {
    const existingZones = await prisma.zone.findMany({
      where: { id: { in: zoneIds } },
      select: { id: true, building_id: true },
    });
    const zoneMap = new Map(existingZones.map((z) => [z.id, z.building_id]));

    for (const r of readings) {
      if (r.zone_id) {
        if (!zoneMap.has(r.zone_id) || zoneMap.get(r.zone_id) !== r.building_id) {
          const err = new Error(`Zone with id '${r.zone_id}' not found for building '${r.building_id}'.`);
          err.status = 422;
          throw err;
        }
      }
    }
  }

  // 3. Persist batch with duplicate skipping
  const records = readings.map((r) => ({
    building_id: r.building_id,
    zone_id: r.zone_id || null,
    timestamp: r.timestamp instanceof Date ? r.timestamp : new Date(r.timestamp),
    meter_reading_kwh: r.meter_reading_kwh,
    outdoor_temperature_c: r.outdoor_temperature_c ?? null,
    relative_humidity_pct: r.relative_humidity_pct ?? null,
  }));

  const result = await prisma.meterReading.createMany({
    data: records,
    skipDuplicates: true,
  });

  return { stored: result.count };
}

module.exports = {
  ingestReadings,
};

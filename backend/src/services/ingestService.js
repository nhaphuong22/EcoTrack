const prisma = require('../db');
const readingStreamService = require('./readingStreamService');
const anomalyService = require('./anomalyService');

// RETURNING distinguishes committed inserts from rows skipped as duplicates.
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
  const meters = await prisma.meter.findMany({ where: { building_id: { in: buildingIds } } });
  const meterMap = new Map(meters.map((meter) => [`${meter.building_id}:${meter.zone_id || ''}`, meter.id]));
  for (const reading of readings) {
    if (!meterMap.has(`${reading.building_id}:${reading.zone_id || ''}`)) {
      const error = new Error('Meter is not provisioned for this building/zone.');
      error.status = 422;
      throw error;
    }
  }
  const intervalByKey = new Map();
  const records = readings.map((r) => {
    const ts = r.timestamp instanceof Date ? r.timestamp : new Date(r.timestamp);
    if (typeof r.interval_seconds === 'number' && Number.isFinite(r.interval_seconds)) {
      intervalByKey.set(`${r.building_id}:${r.zone_id || ''}:${ts.toISOString()}`, r.interval_seconds);
    }
    return {
      meter_id: meterMap.get(`${r.building_id}:${r.zone_id || ''}`),
      building_id: r.building_id,
      zone_id: r.zone_id || null,
      timestamp: ts,
      meter_reading_kwh: r.meter_reading_kwh,
      outdoor_temperature_c: r.outdoor_temperature_c ?? null,
      relative_humidity_pct: r.relative_humidity_pct ?? null,
    };
  });

  const inserted = await prisma.meterReading.createManyAndReturn({
    data: records,
    skipDuplicates: true,
  });

  // Skip per-reading SSE broadcast & live anomaly scoring for large historical backfill batches.
  if (inserted.length > 0 && inserted.length <= 20) {
    for (const r of inserted) {
      readingStreamService.broadcastReading({
        meter_id: r.meter_id,
        building_id: r.building_id,
        zone_id: r.zone_id,
        timestamp: r.timestamp.toISOString(),
        meter_reading_kwh: r.meter_reading_kwh,
        outdoor_temperature_c: r.outdoor_temperature_c,
        relative_humidity_pct: r.relative_humidity_pct,
      });
    }
    await anomalyService.evaluateLiveReadings(inserted, intervalByKey);
  }

  return { stored: inserted.length };
}

module.exports = {
  ingestReadings,
};

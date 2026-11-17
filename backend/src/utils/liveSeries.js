const prisma = require('../db');

// Aggregate completed UTC hours from meter_readings without double-counting building seeds + zone rows.
async function getHourlyBuildingSeries(buildingId = 'office_tower_01', hoursLimit = 72) {
  if (typeof prisma.meterReading?.findMany !== 'function') return [];
  try {
    const now = new Date();
    const currentHourStart = new Date(Date.UTC(
      now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), now.getUTCHours(), 0, 0, 0
    ));
    const since = new Date(currentHourStart.getTime() - hoursLimit * 3600 * 1000);
    const rows = await prisma.meterReading.findMany({
      where: {
        building_id: buildingId,
        timestamp: { gte: since, lt: currentHourStart },
      },
      orderBy: { timestamp: 'asc' },
    });
    if (!Array.isArray(rows) || rows.length === 0) return [];

    const buckets = new Map();
    for (const r of rows) {
      const d = r.timestamp instanceof Date ? r.timestamp : new Date(r.timestamp);
      const hourKey = new Date(Date.UTC(
        d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate(), d.getUTCHours(), 0, 0, 0
      )).toISOString();
      let bucket = buckets.get(hourKey);
      if (!bucket) {
        bucket = { timestamp: hourKey, zoneSum: 0, zoneCount: 0, totalSum: 0, totalCount: 0, tempSum: 0, tempCount: 0 };
        buckets.set(hourKey, bucket);
      }
      if (r.zone_id) {
        bucket.zoneSum += r.meter_reading_kwh;
        bucket.zoneCount += 1;
      } else {
        bucket.totalSum += r.meter_reading_kwh;
        bucket.totalCount += 1;
      }
      if (typeof r.outdoor_temperature_c === 'number' && Number.isFinite(r.outdoor_temperature_c)) {
        bucket.tempSum += r.outdoor_temperature_c;
        bucket.tempCount += 1;
      }
    }

    return [...buckets.values()]
      .sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp))
      .map((b) => ({
        timestamp: b.timestamp,
        meter_reading_kwh: Number((b.zoneCount > 0 ? b.zoneSum : b.totalSum).toFixed(4)),
        outdoor_temperature_c: b.tempCount > 0 ? Number((b.tempSum / b.tempCount).toFixed(2)) : 26.0,
      }));
  } catch (err) {
    console.warn('Could not aggregate live hourly series from DB:', err.message);
    return [];
  }
}

module.exports = { getHourlyBuildingSeries };

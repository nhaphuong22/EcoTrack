const prisma = require('../db');

// Aggregate completed UTC hours from meter_readings without double-counting building seeds + zone rows.
async function getHourlyBuildingSeries(buildingId = 'office_tower_01', hoursLimit = 72) {
  if (typeof prisma.$queryRaw !== 'function') return [];
  try {
    const now = new Date();
    const currentHourStart = new Date(Date.UTC(
      now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), now.getUTCHours(), 0, 0, 0
    ));
    const since = new Date(currentHourStart.getTime() - hoursLimit * 3600 * 1000);
    // Aggregate in SQL: readings arrive every few seconds, so pulling raw rows into Node took seconds.
    const rows = await prisma.$queryRaw`
      SELECT date_trunc('hour', "timestamp" AT TIME ZONE 'UTC') AS hour,
             SUM(meter_reading_kwh) FILTER (WHERE zone_id IS NOT NULL) AS zone_sum,
             SUM(meter_reading_kwh) FILTER (WHERE zone_id IS NULL) AS total_sum,
             AVG(outdoor_temperature_c) AS temp
        FROM meter_readings
       WHERE building_id = ${buildingId} AND "timestamp" >= ${since} AND "timestamp" < ${currentHourStart}
       GROUP BY 1 ORDER BY 1`;
    if (!Array.isArray(rows) || rows.length === 0) return [];

    // Prefer the zone sum so building-total seed rows are not double counted.
    return rows.map((r) => ({
      timestamp: new Date(r.hour).toISOString(),
      meter_reading_kwh: Number((r.zone_sum ?? r.total_sum ?? 0).toFixed(4)),
      outdoor_temperature_c: r.temp == null ? 26.0 : Number(r.temp.toFixed(2)),
    }));
  } catch (err) {
    console.warn('Could not aggregate live hourly series from DB:', err.message);
    return [];
  }
}

module.exports = { getHourlyBuildingSeries };

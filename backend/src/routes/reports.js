const express = require('express');
const { z } = require('zod');
const prisma = require('../db');

const router = express.Router();

const querySchema = z.object({
  building_id: z.string().min(1).max(50).default('office_tower_01'),
  month: z.string().regex(/^\d{4}-(0[1-9]|1[0-2])$/),
});

function monthRange(value) {
  const [year, month] = value.split('-').map(Number);
  const start = new Date(Date.UTC(year, month - 1, 1));
  const end = new Date(Date.UTC(year, month, 1));
  const previousStart = new Date(Date.UTC(year, month - 2, 1));
  return { start, end, previousStart };
}

function summarize(readings) {
  const values = readings.map((item) => Number(item.meter_reading_kwh) || 0);
  const total = values.reduce((sum, value) => sum + value, 0);
  return {
    total_consumption_kwh: Number(total.toFixed(2)),
    average_daily_kwh: 0,
    peak_demand_kw: values.length ? Number(Math.max(...values).toFixed(2)) : 0,
    reading_count: values.length,
  };
}

function groupByDay(readings) {
  const days = new Map();
  for (const reading of readings) {
    const date = new Date(reading.timestamp).toISOString().slice(0, 10);
    const current = days.get(date) || { date, consumption_kwh: 0, peak_demand_kw: 0, readings: 0 };
    const value = Number(reading.meter_reading_kwh) || 0;
    current.consumption_kwh += value;
    current.peak_demand_kw = Math.max(current.peak_demand_kw, value);
    current.readings += 1;
    days.set(date, current);
  }
  return [...days.values()].map((day) => ({
    ...day,
    consumption_kwh: Number(day.consumption_kwh.toFixed(2)),
    peak_demand_kw: Number(day.peak_demand_kw.toFixed(2)),
  }));
}

// GET /api/v1/reports/monthly?building_id=...&month=YYYY-MM
router.get('/monthly', async (req, res, next) => {
  try {
    const { building_id: buildingId, month } = querySchema.parse(req.query);
    const { start, end, previousStart } = monthRange(month);
    const building = await prisma.building.findUnique({ where: { id: buildingId } });
    if (!building) return res.status(404).json({ detail: 'Building not found.' });

    const [readings, previousReadings, anomalies] = await Promise.all([
      prisma.meterReading.findMany({
        where: { building_id: buildingId, zone_id: null, timestamp: { gte: start, lt: end } },
        orderBy: { timestamp: 'asc' },
      }),
      prisma.meterReading.findMany({
        where: { building_id: buildingId, zone_id: null, timestamp: { gte: previousStart, lt: start } },
      }),
      prisma.anomalyEvent.findMany({
        where: { building_id: buildingId, timestamp: { gte: start, lt: end } },
        orderBy: { timestamp: 'desc' },
      }),
    ]);

    const daily = groupByDay(readings);
    const summary = summarize(readings);
    summary.average_daily_kwh = daily.length
      ? Number((summary.total_consumption_kwh / daily.length).toFixed(2))
      : 0;
    const previous = summarize(previousReadings);
    const comparison = previous.total_consumption_kwh > 0
      ? Number((((summary.total_consumption_kwh - previous.total_consumption_kwh) / previous.total_consumption_kwh) * 100).toFixed(1))
      : null;
    const severity = anomalies.reduce((result, item) => {
      const key = String(item.severity || 'UNKNOWN').toUpperCase();
      result[key] = (result[key] || 0) + 1;
      return result;
    }, {});

    return res.json({
      report_id: `${buildingId}-${month}`,
      generated_at: new Date().toISOString(),
      month,
      building: { id: building.id, name: building.name, location: building.location, timezone: building.timezone },
      summary: {
        ...summary,
        change_vs_previous_month_pct: comparison,
        anomaly_count: anomalies.length,
        estimated_waste_vnd: Math.round(anomalies.reduce((sum, item) => sum + Number(item.snapshot?.estimated_waste_vnd || 0), 0)),
      },
      anomaly_breakdown: severity,
      daily,
    });
  } catch (error) {
    next(error);
  }
});

module.exports = router;
module.exports.monthRange = monthRange;
module.exports.groupByDay = groupByDay;

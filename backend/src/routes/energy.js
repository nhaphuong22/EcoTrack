const express = require('express');
const prisma = require('../db');
const { energyCache } = require('../utils/cache');
const { callAIService } = require('../utils/aiClient');
const { getHourlyBuildingSeries } = require('../utils/liveSeries');
const { z } = require('zod');
const { requireRole } = require('../middleware/requireUser');

const router = express.Router();

// GET /api/v1/energy/metrics
router.get('/metrics', async (req, res, next) => {
  try {
    const cacheKey = 'energy_metrics_summary';
    const cached = energyCache.get(cacheKey);

    if (cached !== null) {
      res.setHeader('X-Cache', 'HIT');
      return res.json(cached);
    }

    res.setHeader('X-Cache', 'MISS');
    const series = await getHourlyBuildingSeries('office_tower_01', 720);
    if (series.length >= 24 && typeof prisma.anomalyEvent?.findMany === 'function') {
      const thirtyDaysAgo = new Date(Date.now() - 720 * 3600 * 1000);
      const events = await prisma.anomalyEvent.findMany({
        where: {
          building_id: 'office_tower_01',
          status: { not: 'IGNORED' },
          timestamp: { gte: thirtyDaysAgo },
        },
      });
      const totalConsumption = series.reduce((sum, p) => sum + p.meter_reading_kwh, 0);
      const peakDemand = Math.max(...series.map((p) => p.meter_reading_kwh));
      const wasteVnd = events.reduce((sum, ev) => sum + Number(ev?.snapshot?.estimated_waste_vnd ?? 0), 0);
      const wasteUsd = events.reduce((sum, ev) => sum + Number(ev?.snapshot?.estimated_waste_usd ?? 0), 0);
      const liveMetrics = {
        building_id: 'office_tower_01',
        source: 'live_db',
        total_consumption_kwh: Number(totalConsumption.toFixed(1)),
        peak_demand_kw: Number(peakDemand.toFixed(1)),
        total_anomalies_detected: events.length,
        estimated_waste_cost_vnd: Math.round(wasteVnd),
        estimated_waste_cost_usd: Number(wasteUsd.toFixed(2)),
      };
      energyCache.set(cacheKey, liveMetrics);
      return res.json(liveMetrics);
    }

    const data = await callAIService('/internal/energy/metrics');
    energyCache.set(cacheKey, data);
    res.json(data);
  } catch (err) {
    next(err);
  }
});

// GET /api/v1/energy/timeseries
router.get('/timeseries', async (req, res, next) => {
  try {
    const limit = z.coerce.number().int().min(1).max(720).default(168).parse(req.query.limit);
    const cacheKey = `energy_timeseries_limit_${limit}`;
    const cached = energyCache.get(cacheKey);

    if (cached !== null) {
      res.setHeader('X-Cache', 'HIT');
      return res.json(cached);
    }

    res.setHeader('X-Cache', 'MISS');
    const series = await getHourlyBuildingSeries('office_tower_01', Math.max(limit + 24, 72));
    const data = series.length >= 25
      ? await callAIService(`/internal/energy/timeseries?limit=${limit}`, {
          method: 'POST',
          body: { building_id: 'office_tower_01', recent_readings: series },
        })
      : await callAIService(`/internal/energy/timeseries?limit=${limit}`);
    energyCache.set(cacheKey, data);
    res.json(data);
  } catch (err) {
    next(err);
  }
});

// GET /api/v1/energy/cache/stats
router.get('/cache/stats', (req, res) => {
  res.json(energyCache.getStats());
});

// POST /api/v1/energy/cache/clear
router.post('/cache/clear', requireRole('ADMIN'), (req, res) => {
  energyCache.clear();
  res.json({ message: 'Energy TTL cache invalidated successfully.' });
});

module.exports = router;

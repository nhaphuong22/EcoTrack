const express = require('express');
const { energyCache } = require('../utils/cache');
const { callAIService } = require('../utils/aiClient');
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
    const data = await callAIService(`/internal/energy/timeseries?limit=${limit}`);
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

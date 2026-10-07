const express = require('express');
const { energyCache } = require('../utils/cache');
const { callAIService } = require('../utils/aiClient');

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
    const limit = parseInt(req.query.limit || '168', 10);
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
router.post('/cache/clear', (req, res) => {
  energyCache.clear();
  res.json({ message: 'Energy TTL cache invalidated successfully.' });
});

module.exports = router;

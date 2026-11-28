const express = require('express');
const { z } = require('zod');
const { callAIService } = require('../utils/aiClient');
const { getHourlyBuildingSeries } = require('../utils/liveSeries');

const router = express.Router();

// GET /api/v1/forecast/predict
router.get('/predict', async (req, res, next) => {
  try {
    const series = await getHourlyBuildingSeries('office_tower_01', 72);
    if (series.length >= 24) {
      const data = await callAIService('/internal/forecast/predict', {
        method: 'POST',
        body: { building_id: 'office_tower_01', recent_readings: series },
      });
      return res.json(data);
    }
    const data = await callAIService('/internal/forecast/predict');
    res.json(data);
  } catch (err) {
    next(err);
  }
});

const WhatIfSchema = z.object({
  setpoint_delta_c: z.number().min(0).max(2).multipleOf(0.5).default(0),
  chiller_off_hours: z.number().int().min(0).max(3).default(0),
  hvac_share: z.number().min(0.05).max(0.8).default(0.5),
});

// POST /api/v1/forecast/whatif
router.post('/whatif', async (req, res, next) => {
  const parsed = WhatIfSchema.safeParse(req.body ?? {});
  if (!parsed.success) {
    return res.status(400).json({
      detail: parsed.error.issues.map((e) => ({ loc: e.path, msg: `${e.path.join('.')}: ${e.message}` })),
    });
  }
  try {
    const series = await getHourlyBuildingSeries('office_tower_01', 72);
    const body = { building_id: 'office_tower_01', ...parsed.data };
    if (series.length >= 24) body.recent_readings = series;
    const data = await callAIService('/internal/forecast/whatif', { method: 'POST', body });
    res.json(data);
  } catch (err) {
    next(err);
  }
});

module.exports = router;

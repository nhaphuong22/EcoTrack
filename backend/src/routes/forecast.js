const express = require('express');
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

module.exports = router;

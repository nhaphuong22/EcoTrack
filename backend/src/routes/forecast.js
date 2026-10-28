const express = require('express');
const { callAIService } = require('../utils/aiClient');

const router = express.Router();

// GET /api/v1/forecast/predict
router.get('/predict', async (req, res, next) => {
  try {
    const data = await callAIService('/internal/forecast/predict');
    res.json(data);
  } catch (err) {
    next(err);
  }
});

module.exports = router;

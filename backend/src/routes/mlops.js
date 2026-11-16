const express = require('express');
const requireRole = require('../middleware/requireRole');

const router = express.Router();

// GET /api/v1/mlops/status -> ADMIN, MANAGER
router.get('/status', requireRole('ADMIN', 'MANAGER'), (req, res) => {
  res.json({
    status: 'healthy',
    active_model: 'bdg2_xgboost_v1',
    drift_detected: false,
    metrics: {
      mape: 0.082,
      rmse: 14.5,
    },
    last_retrained: new Date().toISOString(),
  });
});

// POST /api/v1/mlops/retrain -> ADMIN only
router.post('/retrain', requireRole('ADMIN'), (req, res) => {
  res.status(200).json({
    message: 'Model retraining triggered successfully',
    job_id: 'job_retrain_001',
    status: 'IN_PROGRESS',
  });
});

module.exports = router;

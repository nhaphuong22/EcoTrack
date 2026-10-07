const express = require('express');
const { z } = require('zod');
const { updateAnomalyStatus, listAnomalies } = require('../services/anomalyService');

const router = express.Router();

const StatusUpdateSchema = z.object({
  status: z.enum(['OPEN', 'ACKNOWLEDGED', 'RESOLVED', 'IGNORED']),
  note: z.string().optional().nullable(),
});

// GET /api/v1/anomalies/events
router.get('/events', async (req, res, next) => {
  try {
    const events = await listAnomalies();
    res.json(events);
  } catch (err) {
    next(err);
  }
});

// PATCH /api/v1/anomalies/:anomaly_id/status
router.patch('/:anomaly_id/status', async (req, res, next) => {
  try {
    const body = StatusUpdateSchema.parse(req.body);
    const result = await updateAnomalyStatus(req.params.anomaly_id, body.status, body.note);
    res.json(result);
  } catch (err) {
    next(err);
  }
});

module.exports = router;

const express = require('express');
const { z } = require('zod');
const ingestService = require('../services/ingestService');
const { requireApiKey } = require('../middleware/apiKey');

const router = express.Router();

const ReadingItemSchema = z.object({
  building_id: z.string().min(1).max(50),
  zone_id: z.string().min(1).max(50).optional().nullable(),
  timestamp: z.string().datetime({ offset: true }).transform((val) => new Date(val)),
  meter_reading_kwh: z.number().finite().nonnegative(),
  interval_seconds: z.number().finite().positive().max(86400).optional(),
  outdoor_temperature_c: z.number().finite().optional().nullable(),
  relative_humidity_pct: z.number().finite().min(0).max(100).optional().nullable(),
});

const IngestBatchSchema = z.union([
  z.array(ReadingItemSchema).min(1).max(1000),
  z.object({
    readings: z.array(ReadingItemSchema).min(1).max(1000),
  }).transform((val) => val.readings),
]);

// POST /api/v1/ingest/readings
router.post('/readings', requireApiKey('INGEST_API_KEY', 'X-Ingest-Key'), async (req, res, next) => {
  try {
    const readings = IngestBatchSchema.parse(req.body);
    const result = await ingestService.ingestReadings(readings);

    res.status(201).json(result);
  } catch (err) {
    next(err);
  }
});

// GET /api/v1/ingest/targets: which buildings/zones the simulator should stream right now.
router.get('/targets', requireApiKey('INGEST_API_KEY', 'X-Ingest-Key'), async (req, res, next) => {
  try {
    res.json({ buildings: await ingestService.listTargets() });
  } catch (err) {
    next(err);
  }
});

module.exports = router;

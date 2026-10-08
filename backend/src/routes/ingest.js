const express = require('express');
const { z } = require('zod');
const ingestService = require('../services/ingestService');

const router = express.Router();

const ReadingItemSchema = z.object({
  building_id: z.string().min(1).max(50),
  zone_id: z.string().min(1).max(50).optional().nullable(),
  timestamp: z.string().refine((val) => !isNaN(Date.parse(val)), {
    message: 'Invalid datetime format. Expected ISO 8601 string.',
  }).transform((val) => new Date(val)),
  meter_reading_kwh: z.number().nonnegative(),
  outdoor_temperature_c: z.number().optional().nullable(),
  relative_humidity_pct: z.number().optional().nullable(),
});

const IngestBatchSchema = z.union([
  z.array(ReadingItemSchema).min(1),
  z.object({
    readings: z.array(ReadingItemSchema).min(1),
  }).transform((val) => val.readings),
]);

// POST /api/v1/ingest/readings
router.post('/readings', async (req, res, next) => {
  try {
    const expectedKey = process.env.INGEST_API_KEY || 'ecotrack_ingest_secret_2026';
    const providedKey = req.headers['x-ingest-key'];

    if (!providedKey || providedKey !== expectedKey) {
      return res.status(401).json({
        detail: 'Unauthorized: Invalid or missing X-Ingest-Key header.',
      });
    }

    const readings = IngestBatchSchema.parse(req.body);
    const result = await ingestService.ingestReadings(readings);

    res.status(201).json(result);
  } catch (err) {
    next(err);
  }
});

module.exports = router;

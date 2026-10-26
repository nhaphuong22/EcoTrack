const express = require('express');
const { readingEmitter } = require('../services/readingStreamService');

const router = express.Router();

// GET /api/v1/stream/readings?building_id=...
router.get('/readings', (req, res) => {
  const filterBuildingId = req.query.building_id;

  // SSE response headers
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.flushHeaders?.();

  const listener = (reading) => {
    if (!filterBuildingId || reading.building_id === filterBuildingId) {
      res.write(`event: reading\ndata: ${JSON.stringify(reading)}\n\n`);
    }
  };

  readingEmitter.on('reading', listener);

  // Send a comment heartbeat every 15s to keep the connection alive
  const heartbeatInterval = setInterval(() => {
    res.write(': heartbeat\n\n');
  }, 15000);
  heartbeatInterval.unref?.();

  // Clean up on client disconnect
  req.on('close', () => {
    clearInterval(heartbeatInterval);
    readingEmitter.off('reading', listener);
    res.end();
  });
});

module.exports = router;

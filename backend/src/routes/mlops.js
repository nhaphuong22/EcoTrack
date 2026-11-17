const express = require('express');
const { InMemoryTTLCache } = require('../utils/cache');
const { callAIService, AIServiceError } = require('../utils/aiClient');

const router = express.Router();

const positiveInt = (value, fallback) => {
  const n = Number.parseInt(value, 10);
  return Number.isFinite(n) && n > 0 ? n : fallback;
};

const STATUS_KEY = 'mlops_status';
const statusCache = new InMemoryTTLCache(positiveInt(process.env.MLOPS_STATUS_CACHE_TTL_SECONDS, 5));

// shortcut: per-process fixed window keyed by IP, upgrade to a shared store if the gateway runs on several instances.
const retrainWindows = new Map();
function retrainRateLimited(ip) {
  const limit = positiveInt(process.env.MLOPS_RETRAIN_RATE_LIMIT_PER_MINUTE, 3);
  const now = Date.now();
  const win = retrainWindows.get(ip);
  if (!win || now - win.start >= 60000) {
    retrainWindows.set(ip, { start: now, count: 1 });
    return false;
  }
  win.count += 1;
  return win.count > limit;
}

const UPSTREAM_MESSAGES = {
  401: 'The AI service rejected the gateway credentials.',
  403: 'The AI service rejected the gateway credentials.',
};

// Upstream failures are mapped here so an upstream 401/500 never reaches the browser as-is.
// Own failures (unreachable, timeout) carry details === null and keep their status.
function sendUpstreamError(err, res, next) {
  if (!(err instanceof AIServiceError) || err.details === null) return next(err);
  if (err.status === 409) return res.status(409).json(err.details);
  console.error(`AI service returned ${err.status} for MLOps request:`, err.details);
  return res.status(502).json({
    detail: UPSTREAM_MESSAGES[err.status] || 'The AI service returned an error.',
    status: 502,
    upstream_status: err.status,
  });
}

// GET /api/v1/mlops/status
router.get('/status', async (req, res, next) => {
  try {
    const cached = statusCache.get(STATUS_KEY);
    if (cached !== null) {
      res.setHeader('X-Cache', 'HIT');
      return res.json(cached);
    }
    res.setHeader('X-Cache', 'MISS');
    const data = await callAIService('/internal/mlops/status');
    statusCache.set(STATUS_KEY, data);
    res.json(data);
  } catch (err) {
    sendUpstreamError(err, res, next);
  }
});

// POST /api/v1/mlops/retrain — client body is never forwarded.
router.post('/retrain', async (req, res, next) => {
  if (retrainRateLimited(req.ip)) {
    res.setHeader('Retry-After', '60');
    return res.status(429).json({ detail: 'Too many retrain requests. Try again shortly.', status: 429 });
  }
  try {
    const data = await callAIService('/internal/mlops/retrain', { method: 'POST' });
    res.status(202).json(data);
  } catch (err) {
    sendUpstreamError(err, res, next);
  } finally {
    statusCache.clear();
  }
});

// Test hook: reset module state between cases.
router.reset = () => {
  statusCache.clear();
  retrainWindows.clear();
};

module.exports = router;

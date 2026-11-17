require('dotenv').config();
const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const rateLimit = require('express-rate-limit');
const errorHandler = require('./middleware/errorHandler');

const buildingsRouter = require('./routes/buildings');
const energyRouter = require('./routes/energy');
const forecastRouter = require('./routes/forecast');
const anomaliesRouter = require('./routes/anomalies');
const copilotRouter = require('./routes/copilot');
const ingestRouter = require('./routes/ingest');
const streamRouter = require('./routes/stream');
const mlopsRouter = require('./routes/mlops');
const healthRouter = require('./routes/health');
const authRouter = require('./routes/auth');
const portalRouter = require('./routes/portal');
const { requireUser, requirePlatformAdmin } = require('./middleware/requireUser');

function createApp({ authenticate = requireUser } = {}) {
const app = express();

app.use(helmet());
const origins = (process.env.FRONTEND_ORIGIN || 'http://localhost:3000,http://127.0.0.1:3000').split(',').map((value) => value.trim());
app.use(cors({ origin: origins, credentials: true }));
app.use(express.json());
app.use((req, res, next) => {
  res.setHeader('Cache-Control', 'no-store');
  if (!['GET', 'HEAD', 'OPTIONS'].includes(req.method) && req.get('Origin') && !origins.includes(req.get('Origin'))) {
    return res.status(403).json({ detail: 'Origin is not allowed.' });
  }
  next();
});

// Root & Health endpoints (Open)
app.get('/', (req, res) => {
  res.json({
    system: 'EcoTrack BEMS Engine (Express.js Gateway)',
    status: 'operational',
    version: '1.0.0',
    gateway: 'Node.js Express',
  });
});

app.use('/health', healthRouter);
app.use('/api/v1/health', healthRouter);
// Brute-force protection for sign-in and invitation endpoints.
const authLimiter = rateLimit({
  windowMs: 60 * 1000,
  max: process.env.NODE_ENV === 'test' ? 1000 : 30,
  standardHeaders: true,
  legacyHeaders: false,
  message: { detail: 'Too many requests, please try again later.' },
});
app.use('/api/v1/auth', authLimiter, authRouter);
app.use('/api/v1/portal', authenticate, portalRouter);
// Sensor ingestion has a dedicated machine credential. No resident session can
// access unscoped legacy APIs; operators use the scoped portal as well.
app.use('/api/v1/ingest', ingestRouter);
app.use('/api/v1', authenticate, requirePlatformAdmin);

// Mount domain routes under /api/v1
app.use('/api/v1/buildings', buildingsRouter);
app.use('/api/v1/energy', energyRouter);
app.use('/api/v1/forecast', forecastRouter);
app.use('/api/v1/anomalies', anomaliesRouter);
app.use('/api/v1/copilot', copilotRouter);
app.use('/api/v1/stream', streamRouter);
app.use('/api/v1/mlops', mlopsRouter);

// Global Error Handler
app.use(errorHandler);

return app;
}
module.exports = createApp();
module.exports.createApp = createApp;

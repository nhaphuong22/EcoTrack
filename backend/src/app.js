require('dotenv').config();
const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const rateLimit = require('express-rate-limit');
const errorHandler = require('./middleware/errorHandler');
const requireAuth = require('./middleware/requireAuth');

const buildingsRouter = require('./routes/buildings');
const energyRouter = require('./routes/energy');
const forecastRouter = require('./routes/forecast');
const anomaliesRouter = require('./routes/anomalies');
const copilotRouter = require('./routes/copilot');
const ingestRouter = require('./routes/ingest');
const streamRouter = require('./routes/stream');
const healthRouter = require('./routes/health');
const authRouter = require('./routes/auth');
const mlopsRouter = require('./routes/mlops');

const app = express();

// Security Headers
app.use(helmet());

// Configurable CORS
const defaultOrigins = ['http://localhost:3000', 'http://localhost:5173'];
const configuredOrigins = process.env.CORS_ORIGINS
  ? process.env.CORS_ORIGINS.split(',').map((s) => s.trim())
  : defaultOrigins;

app.use(
  cors({
    origin: (origin, callback) => {
      if (!origin || configuredOrigins.includes(origin) || process.env.NODE_ENV === 'test') {
        return callback(null, true);
      }
      return callback(new Error('CORS not allowed for this origin.'));
    },
    credentials: true,
  })
);

app.use(express.json());

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

// Auth Rate Limiting (protect against brute force credential stuffing)
const authLimiter = rateLimit({
  windowMs: 60 * 1000, // 1 minute
  max: process.env.NODE_ENV === 'test' ? 1000 : 30, // 30 req/min in prod
  standardHeaders: true,
  legacyHeaders: false,
  message: { error: 'Too many requests, please try again later.' },
});

// Auth Routes (Open, rate-limited)
app.use('/api/v1/auth', authLimiter, authRouter);

// Ingest Route (Guarded by X-Ingest-Key for IoT sensors)
app.use('/api/v1/ingest', ingestRouter);

// Domain Routes (require authentication)
app.use('/api/v1/buildings', requireAuth, buildingsRouter);
app.use('/api/v1/energy', requireAuth, energyRouter);
app.use('/api/v1/forecast', requireAuth, forecastRouter);
app.use('/api/v1/anomalies', requireAuth, anomaliesRouter);
app.use('/api/v1/copilot', requireAuth, copilotRouter);
app.use('/api/v1/stream', requireAuth, streamRouter);
app.use('/api/v1/mlops', requireAuth, mlopsRouter);

// Global Error Handler
app.use(errorHandler);

module.exports = app;

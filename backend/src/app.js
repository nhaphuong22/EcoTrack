require('dotenv').config();
const express = require('express');
const cors = require('cors');
const errorHandler = require('./middleware/errorHandler');

const buildingsRouter = require('./routes/buildings');
const energyRouter = require('./routes/energy');
const forecastRouter = require('./routes/forecast');
const anomaliesRouter = require('./routes/anomalies');
const copilotRouter = require('./routes/copilot');

const app = express();

app.use(cors());
app.use(express.json());

// Root & Health endpoints
app.get('/', (req, res) => {
  res.json({
    system: 'EcoTrack BEMS Engine (Express.js Gateway)',
    status: 'operational',
    version: '1.0.0',
    gateway: 'Node.js Express',
  });
});

app.get('/health', (req, res) => {
  res.json({ status: 'healthy', timestamp: new Date().toISOString() });
});

// Mount domain routes under /api/v1
app.use('/api/v1/buildings', buildingsRouter);
app.use('/api/v1/energy', energyRouter);
app.use('/api/v1/forecast', forecastRouter);
app.use('/api/v1/anomalies', anomaliesRouter);
app.use('/api/v1/copilot', copilotRouter);

// Global Error Handler
app.use(errorHandler);

module.exports = app;

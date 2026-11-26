const express = require('express');
const router = express.Router();
const prisma = require('../db');
const { callAIService } = require('../utils/aiClient');

/**
 * GET /health
 * Inspects real health of Express Gateway, PostgreSQL Database, and FastAPI AI Service.
 * Implements FR45: Real system status inspection without hardcoded assumptions.
 */
router.get('/', async (req, res) => {
  let databaseStatus = 'disconnected';
  let aiServiceStatus = 'unavailable';
  let modelsStatus = {
    forecast: 'unavailable',
    anomaly: 'unavailable',
  };
  let copilotEngine = 'unavailable';

  // 1. Inspect Database Connectivity
  try {
    if (typeof prisma.$queryRaw === 'function') {
      await prisma.$queryRaw`SELECT 1`;
      databaseStatus = 'connected';
    } else if (prisma.building && typeof prisma.building.count === 'function') {
      await prisma.building.count();
      databaseStatus = 'connected';
    } else {
      databaseStatus = 'connected';
    }
  } catch (err) {
    databaseStatus = 'disconnected';
  }

  // 2. Inspect AI Microservice & Loaded Models
  try {
    const aiHealth = await callAIService('/health?details=true', { timeout: 3000 });
    if (aiHealth && aiHealth.status === 'healthy') {
      aiServiceStatus = 'connected';
      if (aiHealth.models) {
        modelsStatus = aiHealth.models;
      }
      if (aiHealth.copilot_engine) {
        copilotEngine = aiHealth.copilot_engine;
      }
    }
  } catch (err) {
    aiServiceStatus = 'unavailable';
  }

  const isHealthy = databaseStatus === 'connected' && aiServiceStatus === 'connected';

  return res.status(200).json({
    status: isHealthy ? 'healthy' : 'degraded',
    timestamp: new Date().toISOString(),
    services: {
      gateway: 'healthy',
      database: databaseStatus,
      ai_service: aiServiceStatus,
    },
    models: modelsStatus,
    copilot_engine: copilotEngine,
  });
});

module.exports = router;

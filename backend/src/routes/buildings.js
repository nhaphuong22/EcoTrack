const express = require('express');
const { z } = require('zod');
const buildingService = require('../services/buildingService');
const { requireRole } = require('../middleware/requireUser');

const router = express.Router();

const BuildingCreateSchema = z.object({
  id: z.string().min(1).max(50),
  name: z.string().min(1).max(100),
  building_type: z.string().min(1).max(50).default('Office'),
  total_area_sqm: z.number().positive().optional().nullable(),
  location: z.string().max(100).optional().nullable(),
  timezone: z.string().max(50).refine((value) => {
    try { new Intl.DateTimeFormat('en', { timeZone: value }); return true; } catch { return false; }
  }, 'Invalid timezone').default('UTC'),
});

// GET /api/v1/buildings
router.get('/', async (req, res, next) => {
  try {
    const result = await buildingService.listBuildings();
    res.json(result);
  } catch (err) {
    next(err);
  }
});

// GET /api/v1/buildings/:id
router.get('/:id', async (req, res, next) => {
  try {
    const building = await buildingService.getBuildingById(req.params.id);
    if (!building) {
      return res.status(404).json({
        detail: `Building with id '${req.params.id}' not found.`,
      });
    }
    res.json(building);
  } catch (err) {
    next(err);
  }
});

// POST /api/v1/buildings
router.post('/', requireRole('ADMIN'), async (req, res, next) => {
  try {
    const data = BuildingCreateSchema.parse(req.body);
    const existing = await buildingService.getBuildingById(data.id);
    if (existing) {
      return res.status(409).json({
        detail: `Building with id '${data.id}' already exists.`,
      });
    }
    const created = await buildingService.createBuilding(data);
    res.status(201).json(created);
  } catch (err) {
    next(err);
  }
});

// GET /api/v1/buildings/:id/history
router.get('/:id/history', async (req, res, next) => {
  try {
    const query = z.object({
      limit: z.coerce.number().int().min(1).max(1000).default(168),
      zone_id: z.string().min(1).max(50).optional(),
    }).parse(req.query);
    const history = await buildingService.getBuildingHistory(req.params.id, query.limit, query.zone_id ?? null);
    if (!history) {
      return res.status(404).json({
        detail: `Building with id '${req.params.id}' not found.`,
      });
    }
    res.json(history);
  } catch (err) {
    next(err);
  }
});

// GET /api/v1/buildings/:id/zones
router.get('/:id/zones', async (req, res, next) => {
  try {
    const result = await buildingService.listZonesWithLatest(req.params.id);
    if (!result) {
      return res.status(404).json({
        detail: `Building with id '${req.params.id}' not found.`,
      });
    }
    res.json(result);
  } catch (err) {
    next(err);
  }
});

module.exports = router;

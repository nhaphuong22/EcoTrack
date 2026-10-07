const express = require('express');
const { z } = require('zod');
const buildingService = require('../services/buildingService');

const router = express.Router();

const BuildingCreateSchema = z.object({
  id: z.string().min(1).max(50),
  name: z.string().min(1).max(100),
  building_type: z.string().default('Office'),
  total_area_sqm: z.number().positive().optional().nullable(),
  location: z.string().max(100).optional().nullable(),
  timezone: z.string().default('UTC'),
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
router.post('/', async (req, res, next) => {
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
    const limit = parseInt(req.query.limit || '168', 10);
    const history = await buildingService.getBuildingHistory(req.params.id, Math.min(Math.max(limit, 1), 1000));
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

module.exports = router;

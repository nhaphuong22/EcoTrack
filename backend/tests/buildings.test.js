import { describe, it, expect, vi, beforeEach } from 'vitest';

const mockBuilding1 = {
  id: 'office_tower_01',
  name: 'EcoTrack Headquarter Tower',
  building_type: 'Commercial Office',
  total_area_sqm: 15200.0,
  location: 'Hanoi, Vietnam',
  timezone: 'Asia/Ho_Chi_Minh',
  created_at: new Date('2026-01-01T00:00:00Z'),
};

const mockBuilding2 = {
  id: 'Hog_office_Betsy',
  name: 'Hog Betsy Benchmark Office (BDG2)',
  building_type: 'Office',
  total_area_sqm: 18450.0,
  location: 'Singapore',
  timezone: 'Asia/Singapore',
  created_at: new Date('2026-01-02T00:00:00Z'),
};

const mockPrisma = {
  building: {
    upsert: vi.fn(),
    findMany: vi.fn(),
    findUnique: vi.fn(),
    create: vi.fn(),
  },
  meterReading: {
    count: vi.fn(),
    createMany: vi.fn(),
    findMany: vi.fn(),
  },
  conversation: {
    createMany: vi.fn(),
  },
};

global.__mockPrisma = mockPrisma;

import request from 'supertest';
import app from '../src/app';

describe('CRUD Buildings & History Endpoints in Express Backend', () => {
  beforeEach(() => {
    mockPrisma.building.upsert.mockResolvedValue(mockBuilding1);
    mockPrisma.building.findMany.mockResolvedValue([mockBuilding1, mockBuilding2]);
    mockPrisma.building.findUnique.mockResolvedValue(mockBuilding1);
    mockPrisma.building.create.mockResolvedValue(mockBuilding1);
    mockPrisma.meterReading.count.mockResolvedValue(100);
    mockPrisma.meterReading.createMany.mockResolvedValue({ count: 100 });
    mockPrisma.meterReading.findMany.mockResolvedValue([]);
  });

  describe('GET /api/v1/buildings', () => {
    it('should return list of buildings with total count', async () => {
      const res = await request(app).get('/api/v1/buildings');
      expect(res.status).toBe(200);
      expect(res.body.total).toBe(2);
      expect(res.body.buildings).toHaveLength(2);
      expect(res.body.buildings[0].id).toBe('office_tower_01');
      expect(res.body.buildings[1].id).toBe('Hog_office_Betsy');
    });
  });

  describe('GET /api/v1/buildings/:id', () => {
    it('should return building details when building exists', async () => {
      mockPrisma.building.findUnique.mockResolvedValue(mockBuilding1);

      const res = await request(app).get('/api/v1/buildings/office_tower_01');
      expect(res.status).toBe(200);
      expect(res.body.id).toBe('office_tower_01');
      expect(res.body.name).toBe('EcoTrack Headquarter Tower');
      expect(res.body.total_area_sqm).toBe(15200.0);
    });

    it('should return 404 when building is not found', async () => {
      mockPrisma.building.findUnique.mockResolvedValue(null);

      const res = await request(app).get('/api/v1/buildings/unknown_id');
      expect(res.status).toBe(404);
      expect(res.body.detail).toContain('not found');
    });
  });

  describe('POST /api/v1/buildings', () => {
    it('should create a new building and return 201', async () => {
      const newBuildingPayload = {
        id: 'tower_innovation_02',
        name: 'Innovation Tech Tower',
        building_type: 'Office',
        total_area_sqm: 12500.0,
        location: 'Danang, Vietnam',
        timezone: 'Asia/Ho_Chi_Minh',
      };

      mockPrisma.building.findUnique.mockResolvedValue(null); // not existing yet
      mockPrisma.building.create.mockResolvedValue({
        ...newBuildingPayload,
        created_at: new Date(),
      });

      const res = await request(app)
        .post('/api/v1/buildings')
        .send(newBuildingPayload);

      expect(res.status).toBe(201);
      expect(res.body.id).toBe('tower_innovation_02');
      expect(res.body.name).toBe('Innovation Tech Tower');
    });

    it('should return 409 Conflict when building ID already exists', async () => {
      mockPrisma.building.findUnique.mockResolvedValue(mockBuilding1);

      const res = await request(app)
        .post('/api/v1/buildings')
        .send({
          id: 'office_tower_01',
          name: 'Duplicate Tower',
        });

      expect(res.status).toBe(409);
      expect(res.body.detail).toContain('already exists');
    });

    it('should return 422 Unprocessable Entity when validation fails (missing required name)', async () => {
      const res = await request(app)
        .post('/api/v1/buildings')
        .send({
          id: 'invalid_tower',
          // missing name
        });

      expect(res.status).toBe(422);
      expect(res.body.detail).toBeDefined();
    });
  });

  describe('GET /api/v1/buildings/:id/history', () => {
    it('should return chronological history telemetry points', async () => {
      const mockReadingsDesc = [
        {
          timestamp: new Date('2026-10-08T02:00:00Z'),
          meter_reading_kwh: 185.5,
          outdoor_temperature_c: 29.2,
          relative_humidity_pct: 70.0,
        },
        {
          timestamp: new Date('2026-10-08T01:00:00Z'),
          meter_reading_kwh: 170.0,
          outdoor_temperature_c: 28.5,
          relative_humidity_pct: 72.0,
        },
      ];

      mockPrisma.building.findUnique.mockResolvedValue(mockBuilding1);
      mockPrisma.meterReading.findMany.mockResolvedValue(mockReadingsDesc);

      const res = await request(app).get('/api/v1/buildings/office_tower_01/history?limit=10');
      expect(res.status).toBe(200);
      expect(res.body.building_id).toBe('office_tower_01');
      expect(res.body.count).toBe(2);
      expect(res.body.data).toHaveLength(2);
      // Chronological order: oldest first (01:00 before 02:00)
      expect(res.body.data[0].meter_reading_kwh).toBe(170.0);
      expect(res.body.data[1].meter_reading_kwh).toBe(185.5);
    });

    it('should return 404 when querying history of non-existent building', async () => {
      mockPrisma.building.findUnique.mockResolvedValue(null);

      const res = await request(app).get('/api/v1/buildings/ghost_tower/history');
      expect(res.status).toBe(404);
      expect(res.body.detail).toContain('not found');
    });
  });
});

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

const mockZones = Array.from({ length: 10 }, (_, i) => ({
  id: `z${i + 1}`,
  building_id: 'office_tower_01',
  floor: 1,
  name: `Tầng 1 - Phòng ${101 + i}`,
  created_at: new Date('2026-01-01T00:00:00Z'),
  meter_readings: i === 0
    ? [
        {
          timestamp: new Date('2026-10-08T12:00:00Z'),
          meter_reading_kwh: 15.2,
          outdoor_temperature_c: 28.5,
          relative_humidity_pct: 65.0,
        },
      ]
    : [],
}));

const mockPrisma = {
  building: {
    upsert: vi.fn(),
    findUnique: vi.fn(),
  },
  zone: {
    upsert: vi.fn(),
    findMany: vi.fn(),
  },
  meterReading: {
    count: vi.fn(),
    createMany: vi.fn(),
  },
};

global.__mockPrisma = mockPrisma;

import request from 'supertest';
import app from '../src/app';

describe('GET /api/v1/buildings/:id/zones', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockPrisma.building.upsert.mockResolvedValue(mockBuilding1);
    mockPrisma.zone.upsert.mockResolvedValue(mockZones[0]);
    mockPrisma.meterReading.count.mockResolvedValue(100);
    mockPrisma.building.findUnique.mockResolvedValue(mockBuilding1);
    mockPrisma.zone.findMany.mockResolvedValue(mockZones);
  });

  it('returns 200 with 10 zones and latest_reading for known building', async () => {
    const res = await request(app).get('/api/v1/buildings/office_tower_01/zones');

    expect(res.status).toBe(200);
    expect(res.body.building_id).toBe('office_tower_01');
    expect(res.body.total).toBe(10);
    expect(res.body.zones).toHaveLength(10);

    // Zone 1 has latest_reading
    expect(res.body.zones[0].id).toBe('z1');
    expect(res.body.zones[0].name).toBe('Tầng 1 - Phòng 101');
    expect(res.body.zones[0].latest_reading).toEqual({
      timestamp: '2026-10-08T12:00:00.000Z',
      meter_reading_kwh: 15.2,
      outdoor_temperature_c: 28.5,
      relative_humidity_pct: 65.0,
    });

    // Zone 2 has null latest_reading
    expect(res.body.zones[1].id).toBe('z2');
    expect(res.body.zones[1].latest_reading).toBeNull();
  });

  it('returns 404 with detail when building does not exist', async () => {
    mockPrisma.building.findUnique.mockResolvedValue(null);

    const res = await request(app).get('/api/v1/buildings/unknown_id/zones');

    expect(res.status).toBe(404);
    expect(res.body.detail).toContain('unknown_id');
  });
});

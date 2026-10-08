import { describe, it, expect, vi, beforeEach } from 'vitest';

const mockPrisma = {
  building: {
    findMany: vi.fn(),
    findUnique: vi.fn(),
  },
  zone: {
    findMany: vi.fn(),
  },
  meterReading: {
    createMany: vi.fn(),
  },
};

global.__mockPrisma = mockPrisma;

import request from 'supertest';
import app from '../src/app';

const VALID_KEY = 'ecotrack_ingest_secret_2026';

describe('POST /api/v1/ingest/readings', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockPrisma.building.findMany.mockResolvedValue([{ id: 'office_tower_01' }]);
    mockPrisma.zone.findMany.mockResolvedValue([
      { id: 'z1', building_id: 'office_tower_01' },
      { id: 'z2', building_id: 'office_tower_01' },
    ]);
    mockPrisma.meterReading.createMany.mockResolvedValue({ count: 2 });
  });

  it('rejects with 401 when X-Ingest-Key is missing', async () => {
    const res = await request(app)
      .post('/api/v1/ingest/readings')
      .send([
        {
          building_id: 'office_tower_01',
          timestamp: '2026-10-08T12:00:00Z',
          meter_reading_kwh: 120.5,
        },
      ]);

    expect(res.status).toBe(401);
    expect(res.body.detail).toContain('X-Ingest-Key');
    expect(mockPrisma.meterReading.createMany).not.toHaveBeenCalled();
  });

  it('rejects with 401 when X-Ingest-Key is wrong', async () => {
    const res = await request(app)
      .post('/api/v1/ingest/readings')
      .set('X-Ingest-Key', 'wrong-key-secret')
      .send([
        {
          building_id: 'office_tower_01',
          timestamp: '2026-10-08T12:00:00Z',
          meter_reading_kwh: 120.5,
        },
      ]);

    expect(res.status).toBe(401);
    expect(res.body.detail).toContain('Unauthorized');
    expect(mockPrisma.meterReading.createMany).not.toHaveBeenCalled();
  });

  it('persists valid batch and returns 201 with stored count (happy path)', async () => {
    const batch = [
      {
        building_id: 'office_tower_01',
        zone_id: 'z1',
        timestamp: '2026-10-08T12:00:00Z',
        meter_reading_kwh: 14.5,
        outdoor_temperature_c: 28.0,
        relative_humidity_pct: 70.0,
      },
      {
        building_id: 'office_tower_01',
        zone_id: 'z2',
        timestamp: '2026-10-08T12:00:00Z',
        meter_reading_kwh: 18.2,
        outdoor_temperature_c: 28.5,
        relative_humidity_pct: 70.0,
      },
    ];

    const res = await request(app)
      .post('/api/v1/ingest/readings')
      .set('X-Ingest-Key', VALID_KEY)
      .send(batch);

    expect(res.status).toBe(201);
    expect(res.body).toEqual({ stored: 2 });
    expect(mockPrisma.meterReading.createMany).toHaveBeenCalledWith({
      data: expect.arrayContaining([
        expect.objectContaining({
          building_id: 'office_tower_01',
          zone_id: 'z1',
          meter_reading_kwh: 14.5,
        }),
      ]),
      skipDuplicates: true,
    });
  });

  it('accepts wrapped { readings: [...] } payload', async () => {
    const res = await request(app)
      .post('/api/v1/ingest/readings')
      .set('X-Ingest-Key', VALID_KEY)
      .send({
        readings: [
          {
            building_id: 'office_tower_01',
            zone_id: 'z1',
            timestamp: '2026-10-08T12:00:00Z',
            meter_reading_kwh: 15.0,
          },
        ],
      });

    expect(res.status).toBe(201);
    expect(res.body.stored).toBe(2);
  });

  it('handles duplicates via skipDuplicates without error', async () => {
    mockPrisma.meterReading.createMany.mockResolvedValue({ count: 0 });

    const res = await request(app)
      .post('/api/v1/ingest/readings')
      .set('X-Ingest-Key', VALID_KEY)
      .send([
        {
          building_id: 'office_tower_01',
          zone_id: 'z1',
          timestamp: '2026-10-08T12:00:00Z',
          meter_reading_kwh: 14.5,
        },
      ]);

    expect(res.status).toBe(201);
    expect(res.body).toEqual({ stored: 0 });
    expect(mockPrisma.meterReading.createMany).toHaveBeenCalledWith(
      expect.objectContaining({ skipDuplicates: true })
    );
  });

  it('rejects with 422 when building does not exist in DB', async () => {
    mockPrisma.building.findMany.mockResolvedValue([]); // building office_tower_01 not found

    const res = await request(app)
      .post('/api/v1/ingest/readings')
      .set('X-Ingest-Key', VALID_KEY)
      .send([
        {
          building_id: 'non_existent_building',
          timestamp: '2026-10-08T12:00:00Z',
          meter_reading_kwh: 100.0,
        },
      ]);

    expect(res.status).toBe(422);
    expect(res.body.detail).toContain('non_existent_building');
    expect(mockPrisma.meterReading.createMany).not.toHaveBeenCalled();
  });

  it('rejects with 422 when zone does not exist for building', async () => {
    mockPrisma.building.findMany.mockResolvedValue([{ id: 'office_tower_01' }]);
    mockPrisma.zone.findMany.mockResolvedValue([]); // zone z99 not found

    const res = await request(app)
      .post('/api/v1/ingest/readings')
      .set('X-Ingest-Key', VALID_KEY)
      .send([
        {
          building_id: 'office_tower_01',
          zone_id: 'z99',
          timestamp: '2026-10-08T12:00:00Z',
          meter_reading_kwh: 100.0,
        },
      ]);

    expect(res.status).toBe(422);
    expect(res.body.detail).toContain('z99');
    expect(mockPrisma.meterReading.createMany).not.toHaveBeenCalled();
  });

  it('rejects with 422 Zod error when payload is malformed', async () => {
    const res = await request(app)
      .post('/api/v1/ingest/readings')
      .set('X-Ingest-Key', VALID_KEY)
      .send([
        {
          building_id: 'office_tower_01',
          // missing timestamp and meter_reading_kwh
        },
      ]);

    expect(res.status).toBe(422);
    expect(res.body.detail).toBeDefined();
    expect(Array.isArray(res.body.detail)).toBe(true);
    expect(mockPrisma.meterReading.createMany).not.toHaveBeenCalled();
  });

  it('rejects with 422 when meter_reading_kwh is negative', async () => {
    const res = await request(app)
      .post('/api/v1/ingest/readings')
      .set('X-Ingest-Key', VALID_KEY)
      .send([
        {
          building_id: 'office_tower_01',
          timestamp: '2026-10-08T12:00:00Z',
          meter_reading_kwh: -5.0,
        },
      ]);

    expect(res.status).toBe(422);
    expect(res.body.detail).toBeDefined();
    expect(mockPrisma.meterReading.createMany).not.toHaveBeenCalled();
  });
});


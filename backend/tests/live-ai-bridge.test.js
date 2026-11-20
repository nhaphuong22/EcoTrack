import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import EventEmitter from 'events';

const mockPrisma = {
  meterReading: {
    findMany: vi.fn(),
  },
  anomalyEvent: {
    findFirst: vi.fn(),
    findMany: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    upsert: vi.fn(),
  },
};
global.__mockPrisma = mockPrisma;

import request from 'supertest';
import app from './helpers/adminApp';
import { getHourlyBuildingSeries } from '../src/utils/liveSeries';
import { evaluateLiveReadings } from '../src/services/anomalyService';
import { readingEmitter } from '../src/services/readingStreamService';
import streamRouter from '../src/routes/stream';

describe('Live DB forecast & live anomaly detection bridge', () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.clearAllMocks();
    mockPrisma.meterReading.findMany.mockResolvedValue([]);
    mockPrisma.anomalyEvent.findFirst.mockResolvedValue(null);
  });

  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it('aggregates completed UTC hours without double-counting building seeds + zone rows', async () => {
    mockPrisma.meterReading.findMany.mockResolvedValueOnce([
      // Hour 1 has both a building seed row (zone_id null) and two zone rows -> prefer zone sum (15 + 25 = 40)
      { timestamp: new Date('2026-11-17T10:00:00Z'), zone_id: null, meter_reading_kwh: 180, outdoor_temperature_c: 26 },
      { timestamp: new Date('2026-11-17T10:00:00Z'), zone_id: 'z1', meter_reading_kwh: 15, outdoor_temperature_c: 28 },
      { timestamp: new Date('2026-11-17T10:03:00Z'), zone_id: 'z2', meter_reading_kwh: 25, outdoor_temperature_c: 30 },
      // Hour 2 has only building seed -> uses 190
      { timestamp: new Date('2026-11-17T11:00:00Z'), zone_id: null, meter_reading_kwh: 190, outdoor_temperature_c: 27 },
    ]);

    const series = await getHourlyBuildingSeries('office_tower_01', 48);
    expect(series).toHaveLength(2);
    expect(series[0]).toEqual({
      timestamp: '2026-11-17T10:00:00.000Z',
      meter_reading_kwh: 40,
      outdoor_temperature_c: 28,
    });
    expect(series[1]).toEqual({
      timestamp: '2026-11-17T11:00:00.000Z',
      meter_reading_kwh: 190,
      outdoor_temperature_c: 27,
    });
  });

  it('uses POST /internal/forecast/predict when >= 24 hourly DB buckets exist', async () => {
    const startMs = Date.now() - 26 * 3600 * 1000;
    const rows = Array.from({ length: 25 }, (_, i) => ({
      timestamp: new Date(startMs + i * 3600 * 1000),
      zone_id: 'z1',
      meter_reading_kwh: 20 + i,
      outdoor_temperature_c: 27,
    }));
    mockPrisma.meterReading.findMany.mockResolvedValueOnce(rows);
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ building_id: 'office_tower_01', horizon_hours: 24, source: 'live_db', forecast: [] }),
    });

    const res = await request(app).get('/api/v1/forecast/predict');
    expect(res.status).toBe(200);
    expect(res.body.source).toBe('live_db');
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/internal/forecast/predict'),
      expect.objectContaining({ method: 'POST' })
    );
    const forecastPayload = JSON.parse(global.fetch.mock.calls[0][1].body);
    expect(forecastPayload).toEqual(expect.objectContaining({
      building_id: 'office_tower_01',
      recent_readings: expect.any(Array),
    }));
  });

  it('persists live anomaly events with 10-min cooldown and emits SSE anomaly event', async () => {
    const now = new Date();
    const prevTs = new Date(now.getTime() - 3000);
    mockPrisma.meterReading.findMany.mockResolvedValue([
      { timestamp: prevTs, meter_reading_kwh: 0.015 },
    ]);

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ([{
        building_id: 'office_tower_01',
        zone_id: 'z3',
        meter_id: 'meter-z3',
        timestamp: now.toISOString(),
        subsystem: 'Khu vực z3 (Live)',
        severity: 'CRITICAL',
        anomaly_score: 0.89,
        actual_kwh: 45.2,
        predicted_kwh: 18.0,
        delta_kwh: 27.2,
        outdoor_temp_c: 36.5,
        estimated_waste_vnd: 84320,
        estimated_waste_usd: 3.4,
        description: 'Live load spike (2.51x expected rate)',
        suggested_action: 'Inspect HVAC',
      }]),
    });

    mockPrisma.anomalyEvent.create.mockImplementation(async ({ data }) => ({
      ...data,
      timestamp: new Date(data.timestamp),
    }));

    // Subscribe SSE client to verify event: anomaly emission
    const req = new EventEmitter();
    req.query = { building_id: 'office_tower_01' };
    const writes = [];
    const res = { setHeader: vi.fn(), flushHeaders: vi.fn(), write: (msg) => writes.push(msg), end: vi.fn() };
    const route = streamRouter.stack.find((s) => s.route?.path === '/readings');
    route.route.stack[0].handle(req, res);

    const intervalMap = new Map([[`office_tower_01:z3:${now.toISOString()}`, 3]]);
    const created = await evaluateLiveReadings([{
      building_id: 'office_tower_01',
      zone_id: 'z3',
      meter_id: 'meter-z3',
      timestamp: now,
      meter_reading_kwh: 0.0377,
      outdoor_temperature_c: 36.5,
    }], intervalMap);

    expect(created).toHaveLength(1);
    const scorePayload = JSON.parse(global.fetch.mock.calls[0][1].body);
    expect(scorePayload).toEqual(expect.objectContaining({ items: expect.any(Array) }));
    expect(created[0].id).toMatch(/^ANOM-LIVE-/);
    expect(mockPrisma.anomalyEvent.create).toHaveBeenCalledTimes(1);
    expect(writes.some((w) => w.startsWith('event: anomaly\n'))).toBe(true);

    // Cooldown: same meter within 10 minutes with lower reading does not create a duplicate row
    mockPrisma.anomalyEvent.findFirst.mockResolvedValueOnce({
      id: created[0].id,
      actual_reading: 45.2,
      anomaly_score: 0.89,
    });
    const dup = await evaluateLiveReadings([{
      building_id: 'office_tower_01',
      zone_id: 'z3',
      meter_id: 'meter-z3',
      timestamp: now,
      meter_reading_kwh: 0.0377,
      outdoor_temperature_c: 36.5,
    }], intervalMap);
    expect(dup).toHaveLength(0);
    expect(mockPrisma.anomalyEvent.create).toHaveBeenCalledTimes(1);

    req.emit('close');
    expect(readingEmitter.listenerCount('anomaly')).toBe(0);
  });

  it('GET /api/v1/energy/metrics aggregates live DB series and active anomalies when >= 24h exist', async () => {
    const startMs = Date.now() - 26 * 3600 * 1000;
    const rows = Array.from({ length: 25 }, (_, i) => ({
      timestamp: new Date(startMs + i * 3600 * 1000),
      zone_id: 'z1',
      meter_reading_kwh: 100 + i,
      outdoor_temperature_c: 26,
    }));
    mockPrisma.meterReading.findMany.mockResolvedValueOnce(rows);
    mockPrisma.anomalyEvent.findMany.mockResolvedValueOnce([
      {
        id: 'ANOM-LIVE-1',
        status: 'OPEN',
        snapshot: { estimated_waste_vnd: 33179, estimated_waste_usd: 1.34 },
      },
    ]);
    await request(app).post('/api/v1/energy/cache/clear');

    const res = await request(app).get('/api/v1/energy/metrics');
    expect(res.status).toBe(200);
    expect(res.body.source).toBe('live_db');
    expect(res.body.total_anomalies_detected).toBe(1);
    expect(res.body.estimated_waste_cost_vnd).toBe(33179);
    expect(res.body.estimated_waste_cost_usd).toBe(1.34);
  });
});

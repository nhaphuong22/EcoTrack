import { meterMock } from './helpers/adminApp';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import request from 'supertest';
import app from './helpers/adminApp';
import sessionApp from '../src/app';
import buildings from '../src/services/buildingService';
import ingest from '../src/services/ingestService';
import anomalies from '../src/services/anomalyService';
import { readingEmitter } from '../src/services/readingStreamService';

const mock = {
  building: { findUnique: vi.fn(), findMany: vi.fn(), upsert: vi.fn() },
  zone: { findMany: vi.fn(), findFirst: vi.fn() },
  meterReading: { findMany: vi.fn(), createManyAndReturn: vi.fn(), createMany: vi.fn() },
  anomalyEvent: { findMany: vi.fn(), findUnique: vi.fn(), upsert: vi.fn(), updateMany: vi.fn() },
  conversation: { createMany: vi.fn() },
};
mock.meter = meterMock;
global.__mockPrisma = mock;
const originalFetch = global.fetch;
const reading = (zone, value = 10) => ({ building_id: 'office_tower_01', zone_id: zone,
  timestamp: new Date('2026-10-31T10:00:00Z'), meter_reading_kwh: value });
const event = { id: 'ANOM-new', building_id: 'office_tower_01', timestamp: '2026-10-31T10:00:00Z',
  actual_kwh: 100, predicted_kwh: 60, delta_kwh: 40, estimated_waste_vnd: 124000,
  severity: 'Critical', anomaly_score: 0.9 };
const record = (overrides = {}) => ({ ...event, timestamp: new Date(event.timestamp),
  actual_reading: 100, status: 'OPEN', severity: 'CRITICAL', status_history: [], ...overrides });

beforeEach(() => {
  vi.resetAllMocks();
  mock.building.findUnique.mockResolvedValue({ id: 'office_tower_01' });
  mock.building.findMany.mockResolvedValue([{ id: 'office_tower_01' }]);
  mock.zone.findMany.mockResolvedValue([{ id: 'z1', building_id: 'office_tower_01' }, { id: 'z2', building_id: 'office_tower_01' }]);
  mock.meterReading.findMany.mockResolvedValue([]);
  mock.anomalyEvent.findMany.mockResolvedValue([]);
  mock.anomalyEvent.upsert.mockResolvedValue({});
  mock.conversation.createMany.mockResolvedValue({ count: 2 });
  global.fetch = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => [event] });
});
afterEach(() => { global.fetch = originalFetch; });

describe('Business regressions', () => {
  it('broadcasts only inserted rows from a partly duplicated batch', async () => {
    mock.meterReading.createManyAndReturn.mockResolvedValue([reading('z2', 20)]);
    const received = [];
    const listener = (row) => received.push(row);
    readingEmitter.on('reading', listener);
    try {
      expect(await ingest.ingestReadings([reading('z1', 999), reading('z2', 20)])).toEqual({ stored: 1 });
      expect(received).toHaveLength(1);
      expect(received[0].zone_id).toBe('z2');
      expect(received[0].meter_reading_kwh).toBe(20);
    } finally { readingEmitter.off('reading', listener); }
  });

  it('does not seed data during history reads and separates totals from zones', async () => {
    await buildings.getBuildingHistory('office_tower_01', 24);
    expect(mock.meterReading.findMany).toHaveBeenLastCalledWith(expect.objectContaining({
      where: { building_id: 'office_tower_01', zone_id: null }, take: 24,
    }));
    mock.zone.findFirst.mockResolvedValue({ id: 'z1' });
    await buildings.getBuildingHistory('office_tower_01', 24, 'z1');
    expect(mock.meterReading.findMany).toHaveBeenLastCalledWith(expect.objectContaining({
      where: { building_id: 'office_tower_01', zone_id: 'z1' },
    }));
    expect(mock.meterReading.createMany).not.toHaveBeenCalled();
    expect(mock.building.upsert).not.toHaveBeenCalled();
    mock.zone.findFirst.mockResolvedValue(null);
    expect(await buildings.getBuildingHistory('office_tower_01', 24, 'foreign-zone')).toBeNull();
  });

  it('returns no rooms for a building with no rooms, including offline demo fallback', async () => {
    mock.zone.findMany.mockResolvedValue([]);
    expect((await buildings.listZonesWithLatest('Hog_office_Betsy')).zones).toEqual([]);
    mock.building.findUnique.mockRejectedValue(new Error('offline'));
    expect((await buildings.listZonesWithLatest('Hog_office_Betsy')).zones).toEqual([]);
    const fallback = await buildings.listZonesWithLatest('office_tower_01');
    expect(fallback.source).toBe('demo_fallback');
    expect(fallback.zones.every((z) => z.building_id === 'office_tower_01')).toBe(true);
  });

  it('persists detection evidence and keeps older unresolved incidents visible', async () => {
    mock.anomalyEvent.findMany.mockResolvedValue([record({ id: 'ANOM-old', snapshot: null })]);
    const result = await anomalies.listAnomalies();
    expect(result.map((item) => item.id)).toEqual(expect.arrayContaining(['ANOM-new', 'ANOM-old']));
    expect(mock.anomalyEvent.upsert).toHaveBeenCalledWith(expect.objectContaining({
      create: expect.objectContaining({ snapshot: event, status_history: [] }), update: {},
    }));
    const old = result.find((item) => item.id === 'ANOM-old');
    expect(old.predicted_kwh).toBeNull();
    expect(old.estimated_waste_vnd).toBeNull();
  });

  it('returns saved predictions and status unchanged when AI is offline', async () => {
    global.fetch.mockRejectedValue(new Error('offline'));
    mock.anomalyEvent.findMany.mockResolvedValue([record({ status: 'RESOLVED', snapshot: event })]);
    const [result] = await anomalies.listAnomalies();
    expect(result.status).toBe('RESOLVED');
    expect(result.predicted_kwh).toBe(60);
    expect(result.estimated_waste_vnd).toBe(124000);
  });

  it('records status notes separately and rejects concurrent overwrites', async () => {
    mock.anomalyEvent.findUnique.mockResolvedValue(record({ suggested_action: 'Original advice' }));
    mock.anomalyEvent.updateMany.mockResolvedValue({ count: 1 });
    await anomalies.updateAnomalyStatus(event.id, 'ACKNOWLEDGED', 'Checking');
    expect(mock.anomalyEvent.updateMany).toHaveBeenCalledWith(expect.objectContaining({
      where: expect.objectContaining({ status_history: { equals: [] } }),
      data: { status: 'ACKNOWLEDGED', status_history: [expect.objectContaining({ note: 'Checking' })] },
    }));
    mock.anomalyEvent.updateMany.mockResolvedValue({ count: 0 });
    await expect(anomalies.updateAnomalyStatus(event.id, 'RESOLVED')).rejects.toMatchObject({ status: 409 });
  });

  it('requires a signed-in operator on mutation endpoints', async () => {
    expect((await request(sessionApp).post('/api/v1/buildings').send({ id: 'x', name: 'x' })).status).toBe(401);
    expect((await request(sessionApp).patch('/api/v1/anomalies/a/status').send({ status: 'RESOLVED' })).status).toBe(401);
    expect((await request(sessionApp).post('/api/v1/energy/cache/clear')).status).toBe(401);
  });

  it('fails closed when ingest credentials are not configured', async () => {
    const previous = process.env.INGEST_API_KEY;
    delete process.env.INGEST_API_KEY;
    try {
      expect((await request(app).post('/api/v1/ingest/readings')
        .set('X-Ingest-Key', 'ecotrack_ingest_secret_2026').send([reading('z1')])).status).toBe(503);
    } finally { process.env.INGEST_API_KEY = previous; }
  });

  it('generates independent bounded session IDs and preserves an explicit session', async () => {
    global.fetch.mockResolvedValue({ ok: true, status: 200, json: async () => ({ reply: 'Hello' }) });
    const chat = (body = {}) => request(app).post('/api/v1/copilot/chat').send({ message: 'Hello', ...body });
    const first = await chat({ building_id: 'b'.repeat(50) });
    const second = await chat();
    expect(first.body.session_id).toHaveLength(36);
    expect(first.body.session_id).not.toBe(second.body.session_id);
    expect(first.body.conversation_saved).toBe(true);
    const third = await chat({ session_id: first.body.session_id });
    expect(third.body.session_id).toBe(first.body.session_id);
  });

  it('validates history and energy limits rather than returning fake fallback on malformed input', async () => {
    for (const endpoint of ['/api/v1/buildings/office_tower_01/history', '/api/v1/energy/timeseries']) {
      expect((await request(app).get(`${endpoint}?limit=abc`)).status).toBe(422);
      expect((await request(app).get(`${endpoint}?limit=-1`)).status).toBe(422);
    }
  });
});

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const mockPrisma = { $queryRaw: vi.fn() };
global.__mockPrisma = mockPrisma;

import request from 'supertest';
import app from './helpers/adminApp';

describe('POST /api/v1/forecast/whatif', () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    mockPrisma.$queryRaw.mockReset();
    mockPrisma.$queryRaw.mockResolvedValue([]);
  });

  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it.each([
    [{ setpoint_delta_c: 3 }, 'setpoint_delta_c'],
    [{ setpoint_delta_c: 0.7 }, 'setpoint_delta_c'],
    [{ chiller_off_hours: 5 }, 'chiller_off_hours'],
    [{ chiller_off_hours: 1.5 }, 'chiller_off_hours'],
    [{ hvac_share: 0.9 }, 'hvac_share'],
    [{ setpoint_delta_c: 'abc' }, 'setpoint_delta_c'],
  ])('rejects %j with 400 naming the field', async (body, field) => {
    global.fetch = vi.fn();
    const res = await request(app).post('/api/v1/forecast/whatif').send(body);
    expect(res.status).toBe(400);
    expect(JSON.stringify(res.body.detail)).toContain(field);
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it('forwards the validated scenario to the AI service with defaults', async () => {
    const mockResult = { savings: { low: { kwh: 33 }, high: { kwh: 44 } } };
    global.fetch = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => mockResult });

    const res = await request(app).post('/api/v1/forecast/whatif').send({ setpoint_delta_c: 1 });
    expect(res.status).toBe(200);
    expect(res.body).toEqual(mockResult);
    const [url, opts] = global.fetch.mock.calls[0];
    expect(url).toContain('/internal/forecast/whatif');
    expect(opts.method).toBe('POST');
    expect(opts.headers['X-Internal-Token']).toBe(process.env.INTERNAL_API_KEY);
    expect(JSON.parse(opts.body)).toMatchObject({
      building_id: 'office_tower_01', setpoint_delta_c: 1, chiller_off_hours: 0, hvac_share: 0.5,
    });
  });

  it('passes a 503 from the AI service through', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false, status: 503, json: async () => ({ code: 'ERR_MODEL_NOT_FOUND' }),
    });
    const res = await request(app).post('/api/v1/forecast/whatif').send({});
    expect(res.status).toBe(503);
  });

  it('forwards recent_readings when the live series has >= 24 hourly buckets', async () => {
    const startMs = Date.now() - 26 * 3600 * 1000;
    mockPrisma.$queryRaw.mockResolvedValueOnce(Array.from({ length: 25 }, (_, i) => ({
      hour: new Date(startMs + i * 3600 * 1000), zone_sum: 20 + i, total_sum: null, temp: 27,
    })));
    global.fetch = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ source: 'live_db' }) });

    const res = await request(app).post('/api/v1/forecast/whatif').send({ chiller_off_hours: 1 });
    expect(res.status).toBe(200);
    const body = JSON.parse(global.fetch.mock.calls[0][1].body);
    expect(body.recent_readings).toHaveLength(25);
    expect(body.recent_readings[0]).toMatchObject({ meter_reading_kwh: 20, outdoor_temperature_c: 27 });
  });
});

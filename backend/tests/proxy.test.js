import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import request from 'supertest';
import app from '../src/app';
import prisma from '../src/db';

describe('Express Proxy Routes with Mocked Fetch', () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    // Clear cache before each test
    request(app).post('/api/v1/energy/cache/clear');
    vi.spyOn(prisma.conversation, 'createMany').mockResolvedValue({ count: 2 });
  });

  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it('GET /api/v1/forecast/predict should proxy forecast to AI engine', async () => {
    const mockForecast = {
      building_id: 'office_tower_01',
      horizon_hours: 24,
      forecast: [{ timestamp: '2026-10-08T00:00:00Z', predicted_kwh: 155.0 }],
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockForecast,
    });

    const res = await request(app).get('/api/v1/forecast/predict');
    expect(res.status).toBe(200);
    expect(res.body.building_id).toBe('office_tower_01');
    expect(res.body.forecast[0].predicted_kwh).toBe(155.0);
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/internal/forecast/predict'),
      expect.objectContaining({
        headers: expect.objectContaining({
          'X-Internal-Token': process.env.INTERNAL_API_KEY,
        }),
      })
    );
  });

  it('GET /api/v1/energy/metrics should proxy metrics and set X-Cache MISS then HIT', async () => {
    const mockMetrics = {
      building_id: 'office_tower_01',
      total_consumption_kwh: 50000,
      peak_demand_kw: 240,
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockMetrics,
    });

    // Clear cache first
    await request(app).post('/api/v1/energy/cache/clear');

    // First request -> MISS
    const res1 = await request(app).get('/api/v1/energy/metrics');
    expect(res1.status).toBe(200);
    expect(res1.headers['x-cache']).toBe('MISS');
    expect(res1.body.total_consumption_kwh).toBe(50000);

    // Second request -> HIT (should not call fetch again)
    const res2 = await request(app).get('/api/v1/energy/metrics');
    expect(res2.status).toBe(200);
    expect(res2.headers['x-cache']).toBe('HIT');
    expect(global.fetch).toHaveBeenCalledTimes(1);
  });

  it('POST /api/v1/copilot/chat should proxy conversation to AI Copilot', async () => {
    const mockReply = {
      reply: 'Hệ thống HVAC đang hoạt động tối ưu.',
      tools_used: ['query_metrics'],
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockReply,
    });

    const res = await request(app)
      .post('/api/v1/copilot/chat')
      .send({
        message: 'Tình trạng HVAC thế nào?',
        building_id: 'office_tower_01',
        history: [],
      });

    expect(res.status).toBe(200);
    expect(res.body.reply).toBe('Hệ thống HVAC đang hoạt động tối ưu.');
    expect(res.body.tools_used).toContain('query_metrics');
  });
});

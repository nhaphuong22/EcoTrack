import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import request from 'supertest';
import app from '../src/app';

const mockPrisma = {
  $queryRaw: vi.fn(),
};
global.__mockPrisma = mockPrisma;

describe('Express Gateway Smoke & Health Endpoints (Story 2.3)', () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.clearAllMocks();
    mockPrisma.$queryRaw.mockResolvedValue([{ '?column?': 1 }]);
  });

  afterEach(() => {
    global.fetch = originalFetch;
    vi.clearAllMocks();
  });

  it('GET / should return operational status', async () => {
    const res = await request(app).get('/');
    expect(res.status).toBe(200);
    expect(res.body.status).toBe('operational');
    expect(res.body.gateway).toBe('Node.js Express');
  });

  it('GET /health reports fully healthy status when DB and AI service are operational', async () => {
    // Mock healthy AI service
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        status: 'healthy',
        models: {
          forecast: 'loaded',
          anomaly: 'loaded',
        },
        copilot_engine: 'google_genai',
      }),
    });

    const res = await request(app).get('/health');
    expect(res.status).toBe(200);
    expect(res.body.status).toBe('healthy');
    expect(res.body.services.gateway).toBe('healthy');
    expect(res.body.services.database).toBe('connected');
    expect(res.body.services.ai_service).toBe('connected');
    expect(res.body.models.forecast).toBe('loaded');
    expect(res.body.models.anomaly).toBe('loaded');
    expect(res.body.copilot_engine).toBe('google_genai');
  });

  it('GET /health reports degraded status and models unavailable when AI service is offline', async () => {
    // Mock AI service network failure
    global.fetch = vi.fn().mockRejectedValue(new Error('Connection refused'));

    const res = await request(app).get('/health');
    expect(res.status).toBe(200);
    expect(res.body.status).toBe('degraded');
    expect(res.body.services.ai_service).toBe('unavailable');
    expect(res.body.models.forecast).toBe('unavailable');
    expect(res.body.models.anomaly).toBe('unavailable');
    expect(res.body.copilot_engine).toBe('unavailable');
  });

  it('GET /health reports degraded status when database is disconnected', async () => {
    // Mock healthy AI service
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        status: 'healthy',
        models: {
          forecast: 'loaded',
          anomaly: 'loaded',
        },
        copilot_engine: 'rule_based_fallback',
      }),
    });

    // Mock DB failure
    mockPrisma.$queryRaw.mockRejectedValue(new Error('Database offline'));

    const res = await request(app).get('/health');
    expect(res.status).toBe(200);
    expect(res.body.status).toBe('degraded');
    expect(res.body.services.database).toBe('disconnected');
    expect(res.body.services.ai_service).toBe('connected');
  });
});

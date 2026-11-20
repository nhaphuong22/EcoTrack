import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import request from 'supertest';
import app from './helpers/adminApp';
import { createApp } from '../src/app';
import { createRequire } from 'node:module';

// app.js loads the route with Node's require; import the same instance so reset() clears its state.
const mlopsRouter = createRequire(import.meta.url)('../src/routes/mlops');

const upstream = (status, body) => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => body,
});

describe('MLOps gateway proxy', () => {
  const originalFetch = global.fetch;

  beforeEach(() => mlopsRouter.reset());
  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it('forwards status unchanged, including a broken champion, and caches it', async () => {
    const payload = { champion: { status: 'broken', metrics: null, error: 'locked' }, drift: null, retrain_history: [] };
    global.fetch = vi.fn().mockResolvedValue(upstream(200, payload));

    const first = await request(app).get('/api/v1/mlops/status');
    const second = await request(app).get('/api/v1/mlops/status');

    expect(first.status).toBe(200);
    expect(first.body).toEqual(payload);
    expect(first.headers['x-cache']).toBe('MISS');
    expect(second.headers['x-cache']).toBe('HIT');
    expect(global.fetch).toHaveBeenCalledTimes(1);
    expect(global.fetch.mock.calls[0][0]).toContain('/internal/mlops/status');
  });

  it('forwards 202 verbatim, sends no body upstream and clears the status cache', async () => {
    global.fetch = vi.fn().mockResolvedValue(upstream(200, { ok: true }));
    await request(app).get('/api/v1/mlops/status');

    const accepted = { run_id: 'r1', status: 'running', started_at: '2026-11-17T00:00:00Z' };
    global.fetch = vi.fn().mockResolvedValue(upstream(202, accepted));
    const res = await request(app).post('/api/v1/mlops/retrain').send({ evil: 'payload' });

    expect(res.status).toBe(202);
    expect(res.body).toEqual(accepted);
    const [url, init] = global.fetch.mock.calls[0];
    expect(url).toContain('/internal/mlops/retrain');
    expect(init.method).toBe('POST');
    expect(init.body).toBeUndefined();

    global.fetch = vi.fn().mockResolvedValue(upstream(200, { ok: true }));
    const after = await request(app).get('/api/v1/mlops/status');
    expect(after.headers['x-cache']).toBe('MISS');
  });

  it('forwards 409 status and body verbatim', async () => {
    const conflict = { detail: 'Retrain already running', run_id: 'r1' };
    global.fetch = vi.fn().mockResolvedValue(upstream(409, conflict));

    const res = await request(app).post('/api/v1/mlops/retrain');

    expect(res.status).toBe(409);
    expect(res.body).toEqual(conflict);
  });

  it('rate limits retrain with 429 without calling the AI service', async () => {
    global.fetch = vi.fn().mockResolvedValue(upstream(202, { run_id: 'r1' }));
    for (let i = 0; i < 3; i += 1) {
      expect((await request(app).post('/api/v1/mlops/retrain')).status).toBe(202);
    }

    const res = await request(app).post('/api/v1/mlops/retrain');

    expect(res.status).toBe(429);
    expect(res.headers['retry-after']).toBe('60');
    expect(global.fetch).toHaveBeenCalledTimes(3);
  });

  it('lets retrain through again after the rate-limit window passes', async () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    try {
      global.fetch = vi.fn().mockResolvedValue(upstream(202, { run_id: 'r1' }));
      for (let i = 0; i < 3; i += 1) await request(app).post('/api/v1/mlops/retrain');
      expect((await request(app).post('/api/v1/mlops/retrain')).status).toBe(429);

      vi.advanceTimersByTime(61000);

      expect((await request(app).post('/api/v1/mlops/retrain')).status).toBe(202);
    } finally {
      vi.useRealTimers();
    }
  });

  it('maps unreachable to 502 and timeout to 504', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('connect ECONNREFUSED'));
    expect((await request(app).get('/api/v1/mlops/status')).status).toBe(502);

    const abort = Object.assign(new Error('aborted'), { name: 'AbortError' });
    global.fetch = vi.fn().mockRejectedValue(abort);
    expect((await request(app).get('/api/v1/mlops/status')).status).toBe(504);
  });

  it.each([401, 500])('maps upstream %i to 502 without leaking the upstream body', async (code) => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    global.fetch = vi.fn().mockResolvedValue(upstream(code, { detail: 'Traceback /srv/ai-service/secret.py' }));

    const res = await request(app).post('/api/v1/mlops/retrain');

    expect(res.status).toBe(502);
    expect(res.body.upstream_status).toBe(code);
    expect(JSON.stringify(res.body)).not.toContain('secret.py');
  });

  describe('status viewer rule', () => {
    const asUser = (user) => createApp({ authenticate(req, res, next) { req.user = user; next(); } });
    const staff = (building_id, role) => ({ id: 'u', is_platform_admin: false, memberships: [], staff: [{ building_id, role }] });

    it.each([
      ['manager of another building', staff('other_building', 'MANAGER'), 403],
      ['technician of the dashboard building', staff('office_tower_01', 'TECHNICIAN'), 403],
      ['manager of the dashboard building', staff('office_tower_01', 'MANAGER'), 200],
      ['platform admin without staff rows', { id: 'u', is_platform_admin: true, memberships: [], staff: [] }, 200],
    ])('%s gets %i', async (_name, user, code) => {
      global.fetch = vi.fn().mockResolvedValue(upstream(200, { champion: null }));
      expect((await request(asUser(user)).get('/api/v1/mlops/status')).status).toBe(code);
    });

    it('a manager who can view status still cannot retrain', async () => {
      global.fetch = vi.fn();
      const res = await request(asUser(staff('office_tower_01', 'MANAGER'))).post('/api/v1/mlops/retrain');
      expect(res.status).toBe(403);
      expect(global.fetch).not.toHaveBeenCalled();
    });
  });
});

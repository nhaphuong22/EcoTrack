import { describe, it, expect, vi, afterEach } from 'vitest';
import request from 'supertest';
import { createApp } from '../src/app';
import { operatorRole, publicUser } from '../src/services/authService';

const USERS = {
  ADMIN: { id: 'u-admin', is_platform_admin: true, staff: [], memberships: [] },
  MANAGER: { id: 'u-mgr', is_platform_admin: false, staff: [{ building_id: 'b1', role: 'MANAGER' }], memberships: [] },
  TECHNICIAN: { id: 'u-tech', is_platform_admin: false, staff: [{ building_id: 'b1', role: 'TECHNICIAN' }], memberships: [] },
  RESIDENT: { id: 'u-res', is_platform_admin: false, staff: [], memberships: [{ household_id: 'h1' }] },
};

// The test header stands in for a signed-in session of the named kind.
const app = createApp({
  authenticate(req, res, next) {
    req.user = USERS[req.get('x-test-user')];
    if (!req.user) return res.status(401).json({ detail: 'Please sign in.' });
    next();
  },
});
const as = (role) => ({ 'x-test-user': role });

describe('operator roles (Story 5.3)', () => {
  const originalFetch = global.fetch;
  afterEach(() => { global.fetch = originalFetch; vi.restoreAllMocks(); });

  it('derives the role from platform admin and building staff', () => {
    expect(operatorRole(USERS.ADMIN)).toBe('ADMIN');
    expect(operatorRole(USERS.MANAGER)).toBe('MANAGER');
    expect(operatorRole(USERS.TECHNICIAN)).toBe('TECHNICIAN');
    expect(operatorRole(USERS.RESIDENT)).toBeNull();
    expect(publicUser({ ...USERS.MANAGER, name: 'M', email: 'm@x.test' }).role).toBe('MANAGER');
  });

  it('rejects an unauthenticated request with 401 and a resident with 403', async () => {
    expect((await request(app).get('/api/v1/energy/metrics')).status).toBe(401);
    expect((await request(app).get('/api/v1/energy/metrics').set(as('RESIDENT'))).status).toBe(403);
  });

  it('limits mlops status to ADMIN and MANAGER', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ champion: { status: 'resolved' } }) });
    expect((await request(app).get('/api/v1/mlops/status').set(as('TECHNICIAN'))).status).toBe(403);
    expect((await request(app).get('/api/v1/mlops/status').set(as('MANAGER'))).status).toBe(200);
    expect((await request(app).get('/api/v1/mlops/status').set(as('ADMIN'))).status).toBe(200);
  });

  it('limits mlops retrain to ADMIN', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: true, status: 202, json: async () => ({ run_id: 'r1' }) });
    expect((await request(app).post('/api/v1/mlops/retrain').set(as('MANAGER'))).status).toBe(403);
    expect((await request(app).post('/api/v1/mlops/retrain').set(as('TECHNICIAN'))).status).toBe(403);
    expect(global.fetch).not.toHaveBeenCalled();
    expect((await request(app).post('/api/v1/mlops/retrain').set(as('ADMIN'))).status).toBe(202);
  });

  it('limits building creation and cache clearing to ADMIN', async () => {
    for (const role of ['MANAGER', 'TECHNICIAN']) {
      expect((await request(app).post('/api/v1/buildings').set(as(role)).send({})).status).toBe(403);
      expect((await request(app).post('/api/v1/energy/cache/clear').set(as(role))).status).toBe(403);
    }
    expect((await request(app).post('/api/v1/energy/cache/clear').set(as('ADMIN'))).status).toBe(200);
  });

  it('lets a technician reach the anomaly status route (all three roles allowed)', async () => {
    const res = await request(app).patch('/api/v1/anomalies/x/status').set(as('TECHNICIAN')).send({ status: 'bad' });
    expect(res.status).not.toBe(403);
  });
});

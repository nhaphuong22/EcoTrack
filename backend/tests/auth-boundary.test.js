import { describe, it, expect, vi } from 'vitest';
import request from 'supertest';
import app from '../src/app';
import { hashPassword, verifyPassword } from '../src/services/authService';

describe('Account security perimeter', () => {
  it('protects all old and new private read endpoints without a session', async () => {
    for (const path of ['/api/v1/buildings', '/api/v1/energy/metrics', '/api/v1/forecast/predict',
      '/api/v1/anomalies/events', '/api/v1/copilot/experiment-stats', '/api/v1/stream/readings',
      '/api/v1/portal/overview', '/api/v1/portal/zones', '/api/v1/portal/manage', '/api/v1/auth/me']) {
      expect((await request(app).get(path)).status).toBe(401);
    }
  });
  it('blocks cross-origin cookie mutation attempts', async () => {
    expect((await request(app).post('/api/v1/auth/login').set('Origin', 'https://attacker.test')
      .send({ email: 'x@example.test', password: 'LongPassword123' })).status).toBe(403);
  });
  it('uses salted password hashes and rejects a different password', async () => {
    const first = await hashPassword('LongPassword123');
    const second = await hashPassword('LongPassword123');
    expect(first).not.toBe(second);
    expect(first).not.toContain('LongPassword123');
    expect(await verifyPassword('LongPassword123', first)).toBe(true);
    expect(await verifyPassword('WrongPassword123', first)).toBe(false);
  });
});

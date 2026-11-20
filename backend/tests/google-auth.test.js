import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import request from 'supertest';
import express from 'express';
import { createGoogleRouter } from '../src/routes/googleAuth';
import { hashToken } from '../src/services/authService';

const flows = new Map();
const mock = { oAuthFlow: { deleteMany: vi.fn(), create: vi.fn(), findUnique: vi.fn() },
  user: { findUnique: vi.fn(), create: vi.fn(), updateMany: vi.fn() },
  authSession: { create: vi.fn(), findUnique: vi.fn() } };
global.__mockPrisma = mock;
const exchange = vi.fn();
const app = express(); app.use('/api/v1/auth/google', createGoogleRouter({ exchange }));
const keys = ['GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET', 'GOOGLE_REDIRECT_URI', 'APP_FRONTEND_URL'];
let previous;
beforeEach(() => {
  previous = Object.fromEntries(keys.map((key) => [key, process.env[key]]));
  Object.assign(process.env, { GOOGLE_CLIENT_ID: 'test-client', GOOGLE_CLIENT_SECRET: 'test-secret',
    GOOGLE_REDIRECT_URI: 'http://localhost:5000/api/v1/auth/google/callback', APP_FRONTEND_URL: 'http://localhost:3000' });
  vi.resetAllMocks(); flows.clear();
  mock.oAuthFlow.create.mockImplementation(async ({ data }) => { flows.set(data.state_hash, data); return data; });
  mock.oAuthFlow.findUnique.mockImplementation(async ({ where }) => flows.get(where.state_hash) || null);
  mock.oAuthFlow.deleteMany.mockImplementation(async ({ where }) => {
    if (!where.state_hash) return { count: 0 };
    const existed = flows.delete(where.state_hash); return { count: existed ? 1 : 0 };
  });
  mock.user.findUnique.mockResolvedValue(null);
  mock.user.create.mockImplementation(async ({ data }) => ({ ...data, id: 'google-user', active: true }));
  mock.authSession.create.mockResolvedValue({});
  exchange.mockImplementation(async (_, flow) => ({ sub: 'google-subject-1', email: 'alice@example.test',
    email_verified: true, name: 'Alice', nonce: flow.nonce }));
});
afterEach(() => { for (const key of keys) previous[key] === undefined ? delete process.env[key] : process.env[key] = previous[key]; });
async function start(agent) {
  const response = await agent.get('/api/v1/auth/google/start');
  expect(response.status).toBe(302);
  return { response, url: new URL(response.headers.location) };
}
async function callback(agent, url) {
  return agent.get('/api/v1/auth/google/callback').query({ state: url.searchParams.get('state'), code: 'test-authorization-code' });
}

describe('Google account login/registration', () => {
  it('uses state, nonce, PKCE, a bound HttpOnly cookie, and keeps the secret off the authorization URL', async () => {
    const { response, url } = await start(request.agent(app));
    expect(url.origin).toBe('https://accounts.google.com');
    expect(url.searchParams.get('scope')).toBe('openid email profile');
    expect(url.searchParams.get('code_challenge_method')).toBe('S256');
    expect(url.searchParams.get('state')).toHaveLength(64);
    expect(url.searchParams.get('nonce')).toHaveLength(64);
    expect(url.toString()).not.toContain('test-secret');
    expect(response.headers['set-cookie'][0]).toContain('HttpOnly; SameSite=Lax');
  });
  it('creates a Google-only account with no household or administrator privileges', async () => {
    const agent = request.agent(app); const { url } = await start(agent);
    const response = await callback(agent, url);
    expect(response.headers.location).toBe('http://localhost:3000/');
    expect(mock.user.create).toHaveBeenCalledWith({ data: { email: 'alice@example.test', google_sub: 'google-subject-1', name: 'Alice' } });
    expect(mock.authSession.create).toHaveBeenCalled();
    expect(response.headers['set-cookie'].some((value) => value.startsWith('ecotrack_session='))).toBe(true);
  });
  it('logs in a previously linked Google identity', async () => {
    mock.user.findUnique.mockResolvedValue({ id: 'existing-user', email: 'alice@example.test', active: true });
    const agent = request.agent(app); const { url } = await start(agent);
    expect((await callback(agent, url)).headers.location).toBe('http://localhost:3000/');
    expect(mock.user.create).not.toHaveBeenCalled();
  });
  it('does not merge a local email account without an authenticated linking flow', async () => {
    mock.user.findUnique.mockImplementation(async ({ where }) => where.email ? { id: 'local-user' } : null);
    const agent = request.agent(app); const { url } = await start(agent);
    expect((await callback(agent, url)).headers.location).toContain('auth_error=google_link_required');
    expect(mock.authSession.create).not.toHaveBeenCalled();
  });
  it('rejects callbacks from a different browser and rejects state replay', async () => {
    const agent = request.agent(app); const { url } = await start(agent);
    expect((await callback(request.agent(app), url)).headers.location).toContain('google_failed');
    expect(exchange).not.toHaveBeenCalled();
    await callback(agent, url);
    expect((await callback(agent, url)).headers.location).toContain('google_failed');
    expect(exchange).toHaveBeenCalledTimes(1);
  });
  it('rejects expired flows before exchanging a code', async () => {
    const agent = request.agent(app); const { url } = await start(agent);
    flows.get(hashToken(url.searchParams.get('state'))).expires_at = new Date(Date.now() - 1000);
    expect((await callback(agent, url)).headers.location).toContain('google_failed');
    expect(exchange).not.toHaveBeenCalled();
  });
  it.each(['nonce', 'email_verified'])('rejects an invalid identity claim: %s', async (claim) => {
    exchange.mockImplementation(async (_, flow) => ({ sub: 'subject', email: 'alice@example.test',
      email_verified: true, nonce: flow.nonce, [claim]: claim === 'nonce' ? 'wrong-nonce' : false }));
    const agent = request.agent(app); const { url } = await start(agent);
    expect((await callback(agent, url)).headers.location).toContain('google_failed');
    expect(mock.authSession.create).not.toHaveBeenCalled();
  });
  it('links only while the original local account remains signed in', async () => {
    const user = { id: 'local-user', email: 'alice@example.test', active: true };
    mock.authSession.findUnique.mockResolvedValue({ expires_at: new Date(Date.now() + 60000), user });
    mock.user.findUnique.mockImplementation(async ({ where }) => where.id ? user : null);
    mock.user.updateMany.mockResolvedValue({ count: 1 });
    const agent = request.agent(app);
    const response = await agent.get('/api/v1/auth/google/start').set('Cookie', `ecotrack_session=${'a'.repeat(64)}`);
    const url = new URL(response.headers.location);
    const result = await agent.get('/api/v1/auth/google/callback').set('Cookie', [
      response.headers['set-cookie'][0].split(';')[0], `ecotrack_session=${'a'.repeat(64)}`,
    ].join('; ')).query({ state: url.searchParams.get('state'), code: 'code' });
    expect(result.headers.location).toBe('http://localhost:3000/');
    expect(mock.user.updateMany).toHaveBeenCalledWith(expect.objectContaining({ data: { google_sub: 'google-subject-1' } }));
  });
  it('fails closed without provider configuration', async () => {
    delete process.env.GOOGLE_CLIENT_SECRET;
    expect((await request(app).get('/api/v1/auth/google/start')).status).toBe(503);
  });
});

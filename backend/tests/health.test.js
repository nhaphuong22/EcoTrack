import { describe, it, expect } from 'vitest';
import request from 'supertest';
import app from '../src/app';

describe('Express Gateway Smoke & Health Endpoints', () => {
  it('GET / should return operational status', async () => {
    const res = await request(app).get('/');
    expect(res.status).toBe(200);
    expect(res.body.status).toBe('operational');
    expect(res.body.gateway).toBe('Node.js Express');
  });

  it('GET /health should return healthy', async () => {
    const res = await request(app).get('/health');
    expect(res.status).toBe(200);
    expect(res.body.status).toBe('healthy');
    expect(res.body.timestamp).toBeDefined();
  });
});

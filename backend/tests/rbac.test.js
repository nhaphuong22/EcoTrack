import { describe, it, expect, vi, beforeEach } from 'vitest';
import request from 'supertest';
import app from '../src/app';

const mockBuilding1 = {
  id: 'office_tower_01',
  name: 'EcoTrack Headquarter Tower',
  building_type: 'Commercial Office',
  total_area_sqm: 15200.0,
  location: 'Hanoi, Vietnam',
  timezone: 'Asia/Ho_Chi_Minh',
  created_at: new Date('2026-01-01T00:00:00Z'),
};

const mockAnomaly = {
  id: 'ANOM-9999',
  building_id: 'office_tower_01',
  timestamp: new Date(),
  actual_reading: 250.0,
  anomaly_score: -0.15,
  severity: 'WARNING',
  status: 'OPEN',
  detected_at: new Date(),
};

const mockPrisma = {
  building: {
    findMany: vi.fn().mockResolvedValue([mockBuilding1]),
    findUnique: vi.fn().mockResolvedValue(null),
    create: vi.fn().mockResolvedValue(mockBuilding1),
  },
  anomalyEvent: {
    findUnique: vi.fn().mockResolvedValue(mockAnomaly),
    update: vi.fn().mockResolvedValue({ ...mockAnomaly, status: 'ACKNOWLEDGED' }),
    findMany: vi.fn().mockResolvedValue([mockAnomaly]),
  },
};

global.__mockPrisma = mockPrisma;

describe('Story 5.3: RBAC & Gateway Hardening (requireRole, Helmet, CORS, Rate-Limit)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Unauthenticated Request Rejections (401)', () => {
    it('rejects GET /api/v1/buildings without token with 401', async () => {
      const res = await request(app).get('/api/v1/buildings');
      expect(res.status).toBe(401);
      expect(res.body).toEqual({ error: 'Authentication token required' });
    });

    it('rejects GET /api/v1/mlops/status without token with 401', async () => {
      const res = await request(app).get('/api/v1/mlops/status');
      expect(res.status).toBe(401);
      expect(res.body).toEqual({ error: 'Authentication token required' });
    });

    it('rejects POST /api/v1/energy/cache/clear without token with 401', async () => {
      const res = await request(app).post('/api/v1/energy/cache/clear');
      expect(res.status).toBe(401);
    });
  });

  describe('Open Endpoints (Exempt from User Auth)', () => {
    it('GET / and /health stay reachable without any credentials', async () => {
      const resRoot = await request(app).get('/');
      expect(resRoot.status).toBe(200);

      const resHealth = await request(app).get('/health');
      expect(resHealth.status).toBe(200);
    });

    it('POST /api/v1/ingest/readings remains guarded by X-Ingest-Key without user token', async () => {
      const res = await request(app)
        .post('/api/v1/ingest/readings')
        .set('X-Ingest-Key', process.env.INGEST_API_KEY || 'ecotrack_ingest_secret_2026')
        .send([
          {
            building_id: 'office_tower_01',
            timestamp: new Date().toISOString(),
            meter_reading_kwh: 12.5,
          },
        ]);

      // Returns 201 or 422 (if mock), but not 401 user auth required
      expect(res.status).not.toBe(401);
    });
  });

  describe('Role Matrix Enforcement: ADMIN Operations', () => {
    it('POST /api/v1/buildings requires ADMIN; rejects MANAGER and TECHNICIAN with 403', async () => {
      const payload = {
        id: 'new_tower',
        name: 'New Tower',
        building_type: 'Office',
      };

      // TECHNICIAN -> 403
      const resTech = await request(app)
        .post('/api/v1/buildings')
        .set(global.authHeaderFor('TECHNICIAN'))
        .send(payload);
      expect(resTech.status).toBe(403);
      expect(resTech.body).toEqual({ error: 'Forbidden: Insufficient permissions' });

      // MANAGER -> 403
      const resMgr = await request(app)
        .post('/api/v1/buildings')
        .set(global.authHeaderFor('MANAGER'))
        .send(payload);
      expect(resMgr.status).toBe(403);
      expect(resMgr.body).toEqual({ error: 'Forbidden: Insufficient permissions' });

      // ADMIN -> 201
      const resAdmin = await request(app)
        .post('/api/v1/buildings')
        .set(global.authHeaderFor('ADMIN'))
        .send(payload);
      expect(resAdmin.status).toBe(201);
    });

    it('POST /api/v1/energy/cache/clear requires ADMIN; rejects MANAGER and TECHNICIAN with 403', async () => {
      const resTech = await request(app)
        .post('/api/v1/energy/cache/clear')
        .set(global.authHeaderFor('TECHNICIAN'));
      expect(resTech.status).toBe(403);

      const resMgr = await request(app)
        .post('/api/v1/energy/cache/clear')
        .set(global.authHeaderFor('MANAGER'));
      expect(resMgr.status).toBe(403);

      const resAdmin = await request(app)
        .post('/api/v1/energy/cache/clear')
        .set(global.authHeaderFor('ADMIN'));
      expect(resAdmin.status).toBe(200);
      expect(resAdmin.body).toHaveProperty('message');
    });

    it('POST /api/v1/mlops/retrain requires ADMIN; rejects MANAGER and TECHNICIAN with 403', async () => {
      const resTech = await request(app)
        .post('/api/v1/mlops/retrain')
        .set(global.authHeaderFor('TECHNICIAN'));
      expect(resTech.status).toBe(403);

      const resMgr = await request(app)
        .post('/api/v1/mlops/retrain')
        .set(global.authHeaderFor('MANAGER'));
      expect(resMgr.status).toBe(403);

      const resAdmin = await request(app)
        .post('/api/v1/mlops/retrain')
        .set(global.authHeaderFor('ADMIN'));
      expect(resAdmin.status).toBe(200);
      expect(resAdmin.body).toHaveProperty('status', 'IN_PROGRESS');
    });
  });

  describe('Role Matrix Enforcement: MLOps Status & Anomalies', () => {
    it('GET /api/v1/mlops/status allows ADMIN and MANAGER, rejects TECHNICIAN with 403', async () => {
      const resTech = await request(app)
        .get('/api/v1/mlops/status')
        .set(global.authHeaderFor('TECHNICIAN'));
      expect(resTech.status).toBe(403);

      const resMgr = await request(app)
        .get('/api/v1/mlops/status')
        .set(global.authHeaderFor('MANAGER'));
      expect(resMgr.status).toBe(200);
      expect(resMgr.body).toHaveProperty('active_model');

      const resAdmin = await request(app)
        .get('/api/v1/mlops/status')
        .set(global.authHeaderFor('ADMIN'));
      expect(resAdmin.status).toBe(200);
    });

    it('PATCH /api/v1/anomalies/:id/status allows all three roles (ADMIN, MANAGER, TECHNICIAN)', async () => {
      for (const role of ['TECHNICIAN', 'MANAGER', 'ADMIN']) {
        const res = await request(app)
          .patch('/api/v1/anomalies/ANOM-9999/status')
          .set(global.authHeaderFor(role))
          .send({ status: 'ACKNOWLEDGED' });

        expect(res.status).toBe(200);
      }
    });
  });

  describe('Gateway Hardening: Helmet & Headers', () => {
    it('enables Helmet security headers (nosniff, X-Frame-Options, etc.)', async () => {
      const res = await request(app).get('/');
      expect(res.headers['x-content-type-options']).toBe('nosniff');
      expect(res.headers['x-dns-prefetch-control']).toBe('off');
    });
  });
});

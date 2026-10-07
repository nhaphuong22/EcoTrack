import { describe, it, expect, vi, beforeEach } from 'vitest';

const mockAnomaly = {
  id: 'ANOM-1234',
  building_id: 'office_tower_01',
  timestamp: new Date('2026-10-08T00:00:00Z'),
  actual_reading: 245.5,
  anomaly_score: -0.18,
  severity: 'CRITICAL',
  suggested_action: 'Inspect chiller plant schedule and sub-meter power draw.',
  status: 'OPEN',
  detected_at: new Date(),
};

const mockPrisma = {
  anomalyEvent: {
    findUnique: vi.fn(),
    update: vi.fn(),
    findMany: vi.fn(),
    upsert: vi.fn(),
  },
};

global.__mockPrisma = mockPrisma;

import request from 'supertest';
import app from '../src/app';

describe('Anomaly Lifecycle Endpoints in Express Backend', () => {
  beforeEach(() => {
    mockPrisma.anomalyEvent.findUnique.mockResolvedValue(mockAnomaly);
    mockPrisma.anomalyEvent.findMany.mockResolvedValue([mockAnomaly]);
  });

  describe('PATCH /api/v1/anomalies/:id/status', () => {
    it('should update anomaly status from OPEN to ACKNOWLEDGED', async () => {
      mockPrisma.anomalyEvent.update.mockResolvedValue({
        ...mockAnomaly,
        status: 'ACKNOWLEDGED',
      });

      const res = await request(app)
        .patch('/api/v1/anomalies/ANOM-1234/status')
        .send({
          status: 'ACKNOWLEDGED',
          note: 'Operator checking BMS logs.',
        });

      expect(res.status).toBe(200);
      expect(res.body.id).toBe('ANOM-1234');
      expect(res.body.previous_status).toBe('OPEN');
      expect(res.body.current_status).toBe('ACKNOWLEDGED');
      expect(res.body.note).toBe('Operator checking BMS logs.');
    });

    it('should return 422 for invalid status value', async () => {
      const res = await request(app)
        .patch('/api/v1/anomalies/ANOM-1234/status')
        .send({
          status: 'INVALID_STATUS',
        });

      expect(res.status).toBe(422);
    });

    it('should return 404 when anomaly incident does not exist', async () => {
      mockPrisma.anomalyEvent.findUnique.mockResolvedValue(null);

      const res = await request(app)
        .patch('/api/v1/anomalies/NON_EXISTENT/status')
        .send({
          status: 'RESOLVED',
        });

      expect(res.status).toBe(404);
      expect(res.body.detail).toContain('not found');
    });
  });

  describe('GET /api/v1/anomalies/events', () => {
    it('should return list of anomaly events', async () => {
      const res = await request(app).get('/api/v1/anomalies/events');
      expect(res.status).toBe(200);
      expect(Array.isArray(res.body)).toBe(true);
      expect(res.body.length).toBeGreaterThan(0);
      expect(res.body[0].id).toBe('ANOM-1234');
      expect(res.body[0].severity).toBe('CRITICAL');
    });
  });
});

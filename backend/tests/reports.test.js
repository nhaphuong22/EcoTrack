import { describe, it, expect, vi, beforeEach } from 'vitest';
import { meterMock } from './helpers/adminApp';

const mockPrisma = {
  building: { findUnique: vi.fn() },
  meterReading: { findMany: vi.fn() },
  anomalyEvent: { findMany: vi.fn() },
  meter: meterMock,
};
global.__mockPrisma = mockPrisma;

import request from 'supertest';
import app from './helpers/adminApp';

describe('Monthly report endpoint', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockPrisma.building.findUnique.mockResolvedValue({
      id: 'office_tower_01', name: 'EcoTrack Tower', location: 'Ha Noi', timezone: 'Asia/Ho_Chi_Minh',
    });
    mockPrisma.meterReading.findMany
      .mockResolvedValueOnce([
        { timestamp: new Date('2026-10-01T01:00:00Z'), meter_reading_kwh: 100 },
        { timestamp: new Date('2026-10-01T02:00:00Z'), meter_reading_kwh: 120 },
        { timestamp: new Date('2026-10-02T01:00:00Z'), meter_reading_kwh: 80 },
      ])
      .mockResolvedValueOnce([{ timestamp: new Date('2026-09-01T01:00:00Z'), meter_reading_kwh: 250 }]);
    mockPrisma.anomalyEvent.findMany.mockResolvedValue([
      { severity: 'CRITICAL', snapshot: { estimated_waste_vnd: 150000 } },
    ]);
  });

  it('aggregates readings by day and compares with the previous month', async () => {
    const response = await request(app).get('/api/v1/reports/monthly?month=2026-10&building_id=office_tower_01');
    expect(response.status).toBe(200);
    expect(response.body.summary.total_consumption_kwh).toBe(300);
    expect(response.body.summary.average_daily_kwh).toBe(150);
    expect(response.body.summary.change_vs_previous_month_pct).toBe(20);
    expect(response.body.summary.estimated_waste_vnd).toBe(150000);
    expect(response.body.daily).toHaveLength(2);
    expect(response.body.anomaly_breakdown.CRITICAL).toBe(1);
  });

  it('rejects an invalid month', async () => {
    const response = await request(app).get('/api/v1/reports/monthly?month=2026-13');
    expect(response.status).toBe(422);
  });
});

import { describe, it, expect, vi } from 'vitest';
import {
  ZONES,
  loadDataRows,
  sampleTimeAlignedRow,
  generateBatch,
  sendBatch,
  seedBackfill,
  runSimulator,
  parseArgs,
} from '../src/simulator/runSimulator';

describe('Sensor Simulator Bot (runSimulator)', () => {
  it('parses command line arguments correctly', () => {
    const opts = parseArgs([
      '--anomaly-zone', 'z4',
      '--interval', '2000',
      '--building', 'office_tower_01',
      '--once',
    ]);

    expect(opts.anomalyZone).toBe('z4');
    expect(opts.intervalMs).toBe(2000);
    expect(opts.buildingId).toBe('office_tower_01');
    expect(opts.once).toBe(true);
  });

  it('loads data rows from real or fallback dataset', () => {
    const rows = loadDataRows();
    expect(rows.length).toBeGreaterThan(0);
    expect(rows[0]).toHaveProperty('meter_reading');
    expect(rows[0]).toHaveProperty('air_temperature');
    expect(typeof rows[0].meter_reading).toBe('number');
  });

  it('generates a batch of 10 zones with distinct zone_id values', () => {
    const row = { meter_reading: 200.0, air_temperature: 30.0 };
    const options = { buildingId: 'office_tower_01', anomalyZone: null };
    const batch = generateBatch(row, options, '2026-10-08T12:00:00.000Z');

    expect(batch).toHaveLength(10);
    const zoneIds = batch.map((r) => r.zone_id);
    expect(zoneIds).toEqual(ZONES);
    expect(new Set(zoneIds).size).toBe(10);

    for (const reading of batch) {
      expect(reading.building_id).toBe('office_tower_01');
      expect(reading.meter_reading_kwh).toBeGreaterThan(0);
      expect(reading.outdoor_temperature_c).toBeGreaterThan(0);
      expect(reading.timestamp).toBe('2026-10-08T12:00:00.000Z');
    }
  });

  it('amplifies kWh and temperature for the designated anomaly zone', () => {
    const row = { meter_reading: 200.0, air_temperature: 30.0 };
    const normalBatch = generateBatch(row, { buildingId: 'office_tower_01', anomalyZone: null });
    const anomalyBatch = generateBatch(row, { buildingId: 'office_tower_01', anomalyZone: 'z3' });

    const normalZ3 = normalBatch.find((r) => r.zone_id === 'z3');
    const anomalyZ3 = anomalyBatch.find((r) => r.zone_id === 'z3');

    // Anomaly zone z3 should be spiked by 2.5x and +8.5 deg C
    expect(anomalyZ3.meter_reading_kwh).toBeGreaterThan(normalZ3.meter_reading_kwh * 2.0);
    expect(anomalyZ3.outdoor_temperature_c).toBeGreaterThan(normalZ3.outdoor_temperature_c + 7.0);

    // Other zones should remain untouched
    const normalZ1 = normalBatch.find((r) => r.zone_id === 'z1');
    const anomalyZ1 = anomalyBatch.find((r) => r.zone_id === 'z1');
    expect(anomalyZ1.meter_reading_kwh).toBe(normalZ1.meter_reading_kwh);
  });

  it('scales hourly dataset kWh proportionally to tick intervalMs', () => {
    const row = { meter_reading: 200.0, air_temperature: 30.0 };
    const batch3s = generateBatch(row, { buildingId: 'office_tower_01', intervalMs: 3000 });
    const batch1m = generateBatch(row, { buildingId: 'office_tower_01', intervalMs: 60000 });

    const z1ThreeSec = batch3s.find((r) => r.zone_id === 'z1');
    const z1OneMin = batch1m.find((r) => r.zone_id === 'z1');
    // 200 kWh/h * 0.08 * (3000 / 3600000) = 0.0133 kWh; at 60s it is 20x higher (~0.2667 kWh)
    expect(z1ThreeSec.meter_reading_kwh).toBeCloseTo(0.0133, 4);
    expect(z1OneMin.meter_reading_kwh).toBeCloseTo(0.2667, 4);
    expect(z1ThreeSec.interval_seconds).toBe(3);
  });

  it('produces realistic time-of-day curves, weekend scaling, and hourly backfill', async () => {
    const opts = parseArgs([
      '--profile', 'office',
      '--tz', 'Asia/Ho_Chi_Minh',
      '--backfill-hours', '3',
      '--no-jitter',
    ]);
    expect(opts.profile).toBe('office');
    expect(opts.timeZone).toBe('Asia/Ho_Chi_Minh');
    expect(opts.backfillHours).toBe(3);
    expect(opts.jitter).toBe(false);

    // 2026-11-18 is a Wednesday: 03:00+07:00 = 2026-11-17T20:00:00Z, 14:30+07:00 = 2026-11-18T07:30:00Z
    const night = sampleTimeAlignedRow(new Date('2026-11-17T20:00:00Z'), opts);
    const afternoonPeak = sampleTimeAlignedRow(new Date('2026-11-18T07:30:00Z'), opts);
    // 2026-11-22 is Sunday: 14:30+07:00 = 2026-11-22T07:30:00Z
    const weekendAfternoon = sampleTimeAlignedRow(new Date('2026-11-22T07:30:00Z'), opts);

    expect(afternoonPeak.meter_reading).toBeGreaterThan(night.meter_reading * 3);
    expect(afternoonPeak.air_temperature).toBeGreaterThan(night.air_temperature + 5);
    expect(weekendAfternoon.meter_reading).toBeCloseTo(afternoonPeak.meter_reading * 0.45, 1);

    const originalFetch = global.fetch;
    const postedBatches = [];
    global.fetch = vi.fn(async (_url, init) => {
      postedBatches.push(JSON.parse(init.body));
      return { ok: true, status: 201, json: async () => ({ stored: 30 }) };
    });
    try {
      const stored = await seedBackfill(opts, null, new Date('2026-11-18T08:15:00Z'));
      expect(stored).toBe(30);
      expect(postedBatches).toHaveLength(1);
      expect(postedBatches[0]).toHaveLength(33); // 3 hours * (10 zones + 1 BUILDING_TOTAL)
      expect(postedBatches[0][0].interval_seconds).toBe(3600);
      expect(postedBatches[0][0].timestamp).toBe('2026-11-18T05:00:00.000Z');
      const hour1Items = postedBatches[0].slice(0, 10);
      const hour1Total = postedBatches[0][10];
      expect(hour1Total.zone_id).toBeNull();
      expect(hour1Total.meter_reading_kwh).toBeCloseTo(
        hour1Items.reduce((s, r) => s + r.meter_reading_kwh, 0),
        3
      );
      expect(postedBatches[0][22].timestamp).toBe('2026-11-18T07:00:00.000Z');
    } finally {
      global.fetch = originalFetch;
    }
  });

  it('catches network errors gracefully without crashing', async () => {
    // Point to an invalid unreachable port
    const options = {
      gatewayUrl: 'http://localhost:59999',
      apiKey: 'test_key',
    };
    const batch = [{ building_id: 'office_tower_01', zone_id: 'z1', timestamp: '2026-10-08T12:00:00Z', meter_reading_kwh: 10 }];

    const result = await sendBatch(batch, options);
    expect(result.success).toBe(false);
    expect(result).toHaveProperty('error');
  });

  it('runs one tick and completes cleanly when once is set', async () => {
    const logSpy = vi.spyOn(console, 'log').mockImplementation(() => {});
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

    await runSimulator({
      gatewayUrl: 'http://localhost:59999',
      once: true,
      intervalMs: 100,
    });

    logSpy.mockRestore();
    warnSpy.mockRestore();
  });
});

describe('fleet', () => {
  it('streams only the zones the gateway lists, per building', async () => {
    const { runFleet } = await import('../src/simulator/runSimulator');
    const posted = [];
    vi.stubGlobal('fetch', vi.fn(async (url, init) => {
      if (String(url).endsWith('/targets')) {
        return { ok: true, json: async () => ({ buildings: [
          { id: 'residence_01', building_type: 'Residential', timezone: 'Asia/Ho_Chi_Minh', zones: ['z-a', 'z-b'] },
          { id: 'empty_01', building_type: 'Residential', timezone: 'UTC', zones: [] },
        ] }) };
      }
      posted.push(...JSON.parse(init.body));
      return { ok: true, json: async () => ({ stored: 1 }) };
    }));
    vi.spyOn(console, 'log').mockImplementation(() => {});
    await runFleet({ ...parseArgs([]), apiKey: 'k', once: true, backfillHours: 0 });
    vi.unstubAllGlobals();
    expect(new Set(posted.map((r) => r.building_id))).toEqual(new Set(['residence_01']));
    expect(posted.filter((r) => r.zone_id).map((r) => r.zone_id)).toEqual(['z-a', 'z-b']);
  });
});

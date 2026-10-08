import { describe, it, expect, vi } from 'vitest';
import {
  ZONES,
  loadDataRows,
  generateBatch,
  sendBatch,
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

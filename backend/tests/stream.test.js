import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import EventEmitter from 'events';

const mockPrisma = {
  building: {
    findMany: vi.fn(),
  },
  zone: {
    findMany: vi.fn(),
  },
  meterReading: {
    createMany: vi.fn(),
  },
};
global.__mockPrisma = mockPrisma;

import app from '../src/app';
import streamRouter from '../src/routes/stream';
import { readingEmitter, broadcastReading } from '../src/services/readingStreamService';
import ingestService from '../src/services/ingestService';
import * as readingStreamService from '../src/services/readingStreamService';

describe('Story 2.1: Live Readings SSE Stream (/api/v1/stream/readings)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('should be mounted in the Express app under /api/v1/stream', () => {
    const streamLayer = app._router.stack.find(
      (layer) => layer.regexp && layer.regexp.test('/api/v1/stream')
    );
    expect(streamLayer).toBeDefined();
  });

  it('should set proper SSE response headers (Content-Type, Cache-Control, Connection)', () => {
    const req = new EventEmitter();
    req.query = {};
    const res = {
      setHeader: vi.fn(),
      flushHeaders: vi.fn(),
      write: vi.fn(),
      end: vi.fn(),
    };

    const readingRoute = streamRouter.stack.find((s) => s.route?.path === '/readings');
    const handler = readingRoute.route.stack[0].handle;
    handler(req, res);

    expect(res.setHeader).toHaveBeenCalledWith('Content-Type', 'text/event-stream');
    expect(res.setHeader).toHaveBeenCalledWith('Cache-Control', 'no-cache');
    expect(res.setHeader).toHaveBeenCalledWith('Connection', 'keep-alive');
    expect(res.flushHeaders).toHaveBeenCalled();

    req.emit('close');
  });

  it('should deliver broadcasted reading as event: reading within 1 second', () => {
    const req = new EventEmitter();
    req.query = {};
    const res = {
      setHeader: vi.fn(),
      flushHeaders: vi.fn(),
      write: vi.fn(),
      end: vi.fn(),
    };

    const readingRoute = streamRouter.stack.find((s) => s.route?.path === '/readings');
    const handler = readingRoute.route.stack[0].handle;
    handler(req, res);

    const sampleReading = {
      building_id: 'bldg_01',
      zone_id: 'zone_01',
      timestamp: '2026-10-22T13:00:00.000Z',
      meter_reading_kwh: 125.5,
      outdoor_temperature_c: 28.4,
      relative_humidity_pct: 65,
    };

    broadcastReading(sampleReading);

    expect(res.write).toHaveBeenCalledWith(
      `event: reading\ndata: ${JSON.stringify(sampleReading)}\n\n`
    );

    req.emit('close');
  });

  it('should filter events by building_id when query parameter is supplied', () => {
    const req = new EventEmitter();
    req.query = { building_id: 'bldg_target' };
    const res = {
      setHeader: vi.fn(),
      flushHeaders: vi.fn(),
      write: vi.fn(),
      end: vi.fn(),
    };

    const readingRoute = streamRouter.stack.find((s) => s.route?.path === '/readings');
    const handler = readingRoute.route.stack[0].handle;
    handler(req, res);

    const otherReading = {
      building_id: 'bldg_other',
      zone_id: 'zone_03',
      meter_reading_kwh: 45.0,
    };
    const targetReading = {
      building_id: 'bldg_target',
      zone_id: 'zone_02',
      meter_reading_kwh: 80.2,
    };

    broadcastReading(otherReading);
    expect(res.write).not.toHaveBeenCalled();

    broadcastReading(targetReading);
    expect(res.write).toHaveBeenCalledWith(
      `event: reading\ndata: ${JSON.stringify(targetReading)}\n\n`
    );

    req.emit('close');
  });

  it('should send comment heartbeat : heartbeat every 15s to keep connection alive', () => {
    vi.useFakeTimers();

    const req = new EventEmitter();
    req.query = {};
    const res = {
      setHeader: vi.fn(),
      flushHeaders: vi.fn(),
      write: vi.fn(),
      end: vi.fn(),
    };

    const readingRoute = streamRouter.stack.find((s) => s.route?.path === '/readings');
    const handler = readingRoute.route.stack[0].handle;
    handler(req, res);

    vi.advanceTimersByTime(15000);
    expect(res.write).toHaveBeenCalledWith(': heartbeat\n\n');

    vi.advanceTimersByTime(15000);
    expect(res.write).toHaveBeenCalledTimes(2);

    req.emit('close');
  });

  it('should clean up listener and intervals when client disconnects', () => {
    const initialListeners = readingEmitter.listenerCount('reading');

    const req = new EventEmitter();
    req.query = {};
    const res = {
      setHeader: vi.fn(),
      flushHeaders: vi.fn(),
      write: vi.fn(),
      end: vi.fn(),
    };

    const readingRoute = streamRouter.stack.find((s) => s.route?.path === '/readings');
    const handler = readingRoute.route.stack[0].handle;
    handler(req, res);

    expect(readingEmitter.listenerCount('reading')).toBe(initialListeners + 1);

    // Client disconnects
    req.emit('close');

    expect(readingEmitter.listenerCount('reading')).toBe(initialListeners);
    expect(res.end).toHaveBeenCalled();
  });

  it('ingestReadings should broadcast saved readings to the stream emitter', async () => {
    const received = [];
    const listener = (r) => received.push(r);
    readingEmitter.on('reading', listener);

    const mockReadings = [
      {
        building_id: 'bldg_01',
        zone_id: 'zone_01',
        timestamp: new Date('2026-10-22T12:00:00Z'),
        meter_reading_kwh: 120.5,
        outdoor_temperature_c: 29.1,
        relative_humidity_pct: 60,
      },
    ];

    mockPrisma.building.findMany.mockResolvedValueOnce([{ id: 'bldg_01' }]);
    mockPrisma.zone.findMany.mockResolvedValueOnce([{ id: 'zone_01', building_id: 'bldg_01' }]);
    mockPrisma.meterReading.createMany.mockResolvedValueOnce({ count: 1 });

    const result = await ingestService.ingestReadings(mockReadings);

    expect(result.stored).toBe(1);
    expect(received.length).toBe(1);
    expect(received[0]).toEqual(
      expect.objectContaining({
        building_id: 'bldg_01',
        zone_id: 'zone_01',
        meter_reading_kwh: 120.5,
        outdoor_temperature_c: 29.1,
        relative_humidity_pct: 60,
      })
    );

    readingEmitter.off('reading', listener);
  });
});

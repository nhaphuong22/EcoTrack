import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useLiveReadings } from '../hooks/useLiveReadings';

class FakeEventSource {
  static instances = [];
  constructor(url) { this.url = url; FakeEventSource.instances.push(this); }
  addEventListener(_, callback) { this.callback = callback; }
  close() { this.closed = true; }
  emit(reading) { this.callback({ data: JSON.stringify(reading) }); }
}
const zones = [{ id: 'z1', building_id: 'office_tower_01', latest_reading: {
  timestamp: '2026-10-31T10:00:00Z', meter_reading_kwh: 10,
} }];
const reading = (timestamp, value = 20, building = 'office_tower_01') => ({
  zone_id: 'z1', building_id: building, timestamp, meter_reading_kwh: value,
});

beforeEach(() => { FakeEventSource.instances = []; vi.stubGlobal('EventSource', FakeEventSource); });
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

describe('Live readings consistency', () => {
  it('rejects old, equal, malformed, and foreign-building readings', () => {
    const { result } = renderHook(() => useLiveReadings('office_tower_01', zones));
    const source = FakeEventSource.instances[0];
    act(() => source.emit(reading('2026-10-31T10:05:00Z', 25)));
    for (const row of [reading('2026-10-31T09:00:00Z', 999), reading('2026-10-31T10:05:00Z', 999),
      reading('invalid', 999), reading('2026-10-31T10:06:00Z', 999, 'other')]) {
      act(() => source.emit(row));
    }
    expect(result.current.zones[0].latest_reading.meter_reading_kwh).toBe(25);
  });

  it('does not let a stale HTTP refresh overwrite a newer SSE reading', () => {
    const { result, rerender } = renderHook(({ initial }) => useLiveReadings('office_tower_01', initial), {
      initialProps: { initial: zones },
    });
    act(() => FakeEventSource.instances[0].emit(reading('2026-10-31T10:05:00Z', 25)));
    rerender({ initial: [...zones] });
    expect(result.current.zones[0].latest_reading.meter_reading_kwh).toBe(25);
  });

  it('backs off reconnects and discards callbacks from a previous building', () => {
    vi.useFakeTimers();
    const { result, rerender } = renderHook(({ building }) => useLiveReadings(building, zones), {
      initialProps: { building: 'office_tower_01' },
    });
    const first = FakeEventSource.instances[0];
    act(() => first.onerror());
    act(() => vi.advanceTimersByTime(999));
    expect(FakeEventSource.instances).toHaveLength(1);
    act(() => vi.advanceTimersByTime(1));
    act(() => FakeEventSource.instances[1].onerror());
    act(() => vi.advanceTimersByTime(1999));
    expect(FakeEventSource.instances).toHaveLength(2);
    act(() => vi.advanceTimersByTime(1));
    expect(FakeEventSource.instances).toHaveLength(3);
    rerender({ building: 'other' });
    act(() => first.emit(reading('2026-10-31T12:00:00Z', 999)));
    expect(result.current.zones).toEqual([]);
    expect(first.closed).toBe(true);
  });
});

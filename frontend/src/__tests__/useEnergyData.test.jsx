import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useEnergyData } from '../hooks/useEnergyData';
import * as api from '../services/api';

vi.mock('../services/api', () => ({ fetchMetrics: vi.fn(), fetchTimeSeries: vi.fn(),
  fetchAnomalies: vi.fn(), fetchForecast: vi.fn() }));
beforeEach(() => {
  vi.useFakeTimers();
  vi.resetAllMocks();
  api.fetchMetrics.mockResolvedValue({ total_consumption_kwh: 100 });
  api.fetchTimeSeries.mockResolvedValue({ data: [] });
  api.fetchAnomalies.mockResolvedValue([]);
  api.fetchForecast.mockResolvedValue({ forecast: [] });
});
afterEach(() => vi.useRealTimers());

describe('Dashboard startup recovery', () => {
  it('recovers automatically when AI becomes available after an initial 502', async () => {
    api.fetchMetrics.mockRejectedValueOnce({ message: 'AI starting', response: { status: 502 } });
    const { result } = renderHook(() => useEnergyData());
    await act(async () => {});
    expect(result.current.error).toBe('AI starting');
    await act(async () => vi.advanceTimersByTimeAsync(2000));
    expect(result.current.error).toBeNull();
    expect(result.current.metrics.total_consumption_kwh).toBe(100);
  });

  it('does not retry validation errors and cancels pending retries on unmount', async () => {
    api.fetchMetrics.mockRejectedValueOnce({ message: 'Invalid', response: { status: 422 } });
    const first = renderHook(() => useEnergyData());
    await act(async () => {});
    await act(async () => vi.advanceTimersByTimeAsync(2000));
    expect(api.fetchMetrics).toHaveBeenCalledTimes(1);
    first.unmount();
    api.fetchMetrics.mockRejectedValueOnce({ message: 'Offline', response: { status: 502 } });
    const second = renderHook(() => useEnergyData());
    await act(async () => {});
    second.unmount();
    await act(async () => vi.advanceTimersByTimeAsync(5000));
    expect(api.fetchMetrics).toHaveBeenCalledTimes(2);
  });
});

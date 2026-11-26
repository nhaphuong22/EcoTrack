import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import SystemStatus from '../components/dashboard/SystemStatus';
import * as api from '../services/api';

vi.mock('../services/api', () => ({
  fetchSystemHealth: vi.fn(),
}));

describe('SystemStatus - Story 2.3 Real System Status Monitoring (FR45)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('AC1 & AC2: displays all components as healthy/loaded without hardcoded values', async () => {
    api.fetchSystemHealth.mockResolvedValue({
      status: 'healthy',
      timestamp: '2026-10-22T08:00:00Z',
      services: {
        gateway: 'healthy',
        database: 'connected',
        ai_service: 'connected',
      },
      models: {
        forecast: 'loaded',
        anomaly: 'loaded',
      },
      copilot_engine: 'google_genai',
    });

    render(<SystemStatus />);

    await waitFor(() => {
      expect(screen.getByTestId('xgboost-status-text')).toHaveTextContent('Đang chạy');
      expect(screen.getByTestId('isolation_forest-status-text')).toHaveTextContent('Đang chạy');
      expect(screen.getByTestId('copilot-status-text')).toHaveTextContent('Sẵn sàng (google_genai)');
      expect(screen.getByTestId('database-status-text')).toHaveTextContent('Đồng bộ');
      expect(screen.getByTestId('ai_service-status-text')).toHaveTextContent('Trực tuyến');
    });
  });

  it('AC2: reflects degraded component states when models or services are offline', async () => {
    api.fetchSystemHealth.mockResolvedValue({
      status: 'degraded',
      timestamp: '2026-10-22T08:00:00Z',
      services: {
        gateway: 'healthy',
        database: 'disconnected',
        ai_service: 'unavailable',
      },
      models: {
        forecast: 'unavailable',
        anomaly: 'unavailable',
      },
      copilot_engine: 'unavailable',
    });

    render(<SystemStatus />);

    await waitFor(() => {
      expect(screen.getByTestId('xgboost-status-text')).toHaveTextContent('Không khả dụng');
      expect(screen.getByTestId('isolation_forest-status-text')).toHaveTextContent('Không khả dụng');
      expect(screen.getByTestId('copilot-status-text')).toHaveTextContent('Không khả dụng');
      expect(screen.getByTestId('database-status-text')).toHaveTextContent('Mất kết nối');
      expect(screen.getByTestId('ai_service-status-text')).toHaveTextContent('Ngoại tuyến');
    });
  });

  it('AC3: marks every component as "unknown" (Không xác định) when health endpoint is unreachable', async () => {
    api.fetchSystemHealth.mockRejectedValue(new Error('Network error: Gateway unreachable'));

    render(<SystemStatus />);

    await waitFor(() => {
      expect(screen.getByTestId('xgboost-status-text')).toHaveTextContent('Không xác định');
      expect(screen.getByTestId('isolation_forest-status-text')).toHaveTextContent('Không xác định');
      expect(screen.getByTestId('copilot-status-text')).toHaveTextContent('Không xác định');
      expect(screen.getByTestId('database-status-text')).toHaveTextContent('Không xác định');
      expect(screen.getByTestId('ai_service-status-text')).toHaveTextContent('Không xác định');
    });
  });

  it('AC2: refreshes status every 30 seconds automatically', async () => {
    vi.useFakeTimers();

    api.fetchSystemHealth.mockResolvedValue({
      status: 'healthy',
      timestamp: '2026-10-22T08:00:00Z',
      services: { database: 'connected', ai_service: 'connected' },
      models: { forecast: 'loaded', anomaly: 'loaded' },
      copilot_engine: 'rule_based_fallback',
    });

    render(<SystemStatus pollIntervalMs={30000} />);

    // Initial load call
    expect(api.fetchSystemHealth).toHaveBeenCalledTimes(1);

    // Fast-forward 30 seconds
    await act(async () => {
      vi.advanceTimersByTime(30000);
    });

    expect(api.fetchSystemHealth).toHaveBeenCalledTimes(2);

    // Fast-forward another 30 seconds
    await act(async () => {
      vi.advanceTimersByTime(30000);
    });

    expect(api.fetchSystemHealth).toHaveBeenCalledTimes(3);
  });
});

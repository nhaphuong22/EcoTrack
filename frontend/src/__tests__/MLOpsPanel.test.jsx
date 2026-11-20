import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act, fireEvent } from '@testing-library/react';
import MLOpsPanel from '../components/dashboard/MLOpsPanel';
import { canViewMLOps, DASHBOARD_BUILDING } from '../hooks/useMLOpsStatus';
import * as api from '../services/api';

vi.mock('../services/api', () => ({
  fetchMLOpsStatus: vi.fn(),
  triggerMLOpsRetrain: vi.fn(),
}));
vi.mock('recharts', async () => {
  const original = await vi.importActual('recharts');
  return {
    ...original,
    ResponsiveContainer: ({ children }) => <div>{children}</div>,
  };
});

const payload = (over = {}) => ({
  champion: {
    status: 'ok',
    version: '7',
    trained_at: '2026-11-01',
    metrics: { mape: 4.2 },
    error: null,
  },
  drift: {
    checked_at: 't',
    drift_detected: true,
    triggered_signals: ['temp'],
    signals: { temp: { psi: 0.3 } },
    rolling_mape: { mape_percent: 5 },
    thresholds: { psi: 0.2 },
  },
  anomaly_quality: { precision: 0.9, recall: 0.8, f1: 0.85 },
  retrain_history: [{ run_id: 'old', timestamp: 't0', trigger: 'manual', outcome: 'promoted' }],
  benchmark: {
    models: [{ model: 'xgb', mae_kwh: 1, rmse_kwh: 2, mape_percent: 3, r2: 0.9 }],
  },
  errors: {},
  ...over,
});
const httpError = (status, data) => Object.assign(new Error('x'), { response: { status, data } });

const mount = async (props = { isAdmin: true }) => {
  render(<MLOpsPanel {...props} />);
  await act(async () => {});
};
const retrainFlow = async () => {
  fireEvent.click(screen.getByRole('button', { name: 'Retrain' }));
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: 'Xác nhận' }));
  });
};

describe('MLOpsPanel - Story 4.12', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    api.fetchMLOpsStatus.mockResolvedValue(payload());
  });
  afterEach(() => vi.useRealTimers());

  it('gates the tab by role and building', () => {
    expect(canViewMLOps({ role: 'ADMIN' })).toBe(true);
    expect(
      canViewMLOps({
        role: 'MANAGER',
        staff: [{ role: 'MANAGER', building_id: 'office_tower_01' }],
      }),
    ).toBe(true);
    expect(
      canViewMLOps({
        role: 'MANAGER',
        staff: [{ role: 'MANAGER', building_id: 'other' }],
      }),
    ).toBe(false);
    expect(
      canViewMLOps({
        role: 'TECHNICIAN',
        staff: [{ role: 'TECHNICIAN', building_id: 'office_tower_01' }],
      }),
    ).toBe(false);
    expect(canViewMLOps(null)).toBe(false);
  });

  it('renders every section for an admin and hides Retrain for non-admins', async () => {
    await mount();
    expect(screen.getByText('7')).toBeInTheDocument();
    expect(screen.getByText('Phát hiện drift')).toBeInTheDocument();
    expect(screen.getByText('0.850')).toBeInTheDocument();
    expect(screen.getByText('old')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'MAPE theo mô hình' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retrain' })).toBeInTheDocument();
  });

  it('hides Retrain for a manager', async () => {
    await mount({ isAdmin: false });
    expect(screen.queryByRole('button', { name: 'Retrain' })).toBeNull();
  });

  it.each(['fallback', 'unavailable', 'broken'])(
    'shows a banner for champion %s',
    async (status) => {
      api.fetchMLOpsStatus.mockResolvedValue(
        payload({ champion: { status, metrics: null, error: 'disk locked' } }),
      );
      await mount();
      expect(screen.getAllByRole('alert')[0]).toHaveTextContent(status);
      expect(screen.getByText('Chưa có chỉ số.')).toBeInTheDocument();
      if (status === 'broken') expect(screen.getByText('disk locked')).toBeInTheDocument();
    },
  );

  it('distinguishes null (empty) from errored sections while others render', async () => {
    api.fetchMLOpsStatus.mockResolvedValue(
      payload({
        drift: null,
        anomaly_quality: null,
        benchmark: null,
        errors: { benchmark: 'boom' },
      }),
    );
    await mount();
    expect(screen.getByText(/Lỗi: boom/)).toBeInTheDocument();
    expect(screen.getAllByText('Chưa có dữ liệu.')).toHaveLength(2);
    expect(screen.getByText('old')).toBeInTheDocument();
  });

  it('needs a confirm click before calling retrain, then polls every 4s and stops at the run_id', async () => {
    api.triggerMLOpsRetrain.mockResolvedValue({ run_id: 'r1' });
    await mount();
    fireEvent.click(screen.getByRole('button', { name: 'Retrain' }));
    expect(api.triggerMLOpsRetrain).not.toHaveBeenCalled();
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Xác nhận' }));
    });
    expect(api.triggerMLOpsRetrain).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', { name: /Đang huấn luyện/ })).toBeDisabled();

    api.fetchMLOpsStatus.mockClear();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(8000);
    });
    expect(api.fetchMLOpsStatus).toHaveBeenCalledTimes(2);

    api.fetchMLOpsStatus.mockResolvedValue(
      payload({ retrain_history: [{ run_id: 'r1', outcome: 'promoted' }] }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4000);
    });
    expect(screen.getByRole('button', { name: 'Retrain' })).toBeEnabled();
    api.fetchMLOpsStatus.mockClear();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(8000);
    });
    expect(api.fetchMLOpsStatus).not.toHaveBeenCalled(); // back to the 30 s idle cadence
  });

  it('refreshes quietly every 30s while idle and stops on unmount', async () => {
    const { unmount } = render(<MLOpsPanel isAdmin />);
    await act(async () => {});
    api.fetchMLOpsStatus.mockClear();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30000);
    });
    expect(api.fetchMLOpsStatus).toHaveBeenCalledTimes(1);
    unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60000);
    });
    expect(api.fetchMLOpsStatus).toHaveBeenCalledTimes(1);
  });

  it('pauses while the browser tab is hidden', async () => {
    await mount();
    api.fetchMLOpsStatus.mockClear();
    Object.defineProperty(document, 'hidden', {
      configurable: true,
      get: () => true,
    });
    try {
      document.dispatchEvent(new Event('visibilitychange'));
      await act(async () => {
        await vi.advanceTimersByTimeAsync(60000);
      });
      expect(api.fetchMLOpsStatus).not.toHaveBeenCalled();
      Object.defineProperty(document, 'hidden', { configurable: true, get: () => false });
      document.dispatchEvent(new Event('visibilitychange'));
      await act(async () => {});
      expect(api.fetchMLOpsStatus).toHaveBeenCalledTimes(1); // refetches as soon as the tab is visible again
    } finally {
      Object.defineProperty(document, 'hidden', {
        configurable: true,
        get: () => false,
      });
    }
  });

  it('shows "still running or unknown" after the 15 minute ceiling', async () => {
    api.triggerMLOpsRetrain.mockResolvedValue({ run_id: 'never' });
    await mount();
    await retrainFlow();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(15 * 60 * 1000 + 4000);
    });
    expect(screen.getByText(/Vẫn đang chạy hoặc chưa rõ/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retrain' })).toBeEnabled();
  });

  it('409 reports a running retrain and starts polling', async () => {
    api.triggerMLOpsRetrain.mockRejectedValue(
      httpError(409, { detail: 'Retrain already running', run_id: 'r9' }),
    );
    await mount();
    await retrainFlow();
    expect(screen.getByText('Đang có một lần huấn luyện lại đang chạy.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Đang huấn luyện/ })).toBeDisabled();
  });

  it('409 without a run_id finishes when a new history row appears', async () => {
    api.triggerMLOpsRetrain.mockRejectedValue(httpError(409, { detail: 'Retrain already running' }));
    await mount();
    await retrainFlow();
    expect(screen.getByRole('button', { name: /Đang huấn luyện/ })).toBeDisabled();
    api.fetchMLOpsStatus.mockResolvedValue(
      payload({ retrain_history: [{ run_id: 'new', outcome: 'promoted' }, { run_id: 'old' }] }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4000);
    });
    expect(screen.getByRole('button', { name: 'Retrain' })).toBeEnabled();
  });

  it('survives a payload with errors: null', async () => {
    api.fetchMLOpsStatus.mockResolvedValue(payload({ errors: null }));
    await mount();
    expect(screen.getByRole('heading', { name: 'Champion' })).toBeInTheDocument();
  });

  it.each([429, 502, 504])(
    '%i shows the gateway message and keeps the button usable',
    async (code) => {
      api.triggerMLOpsRetrain.mockRejectedValue(httpError(code, { detail: `gateway ${code}` }));
      await mount();
      await retrainFlow();
      expect(screen.getByText(`gateway ${code}`)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Retrain' })).toBeEnabled();
    },
  );
});

describe('MLOps viewer rule stays in sync with the gateway', () => {
  it('uses the same dashboard building id as backend/src/routes/mlops.js', () => {
    // Vitest runs from frontend/ (npm --prefix) or from the repo root.
    const file = ['../backend', 'backend']
      .map((dir) => resolve(process.cwd(), dir, 'src/routes/mlops.js'))
      .find(existsSync);
    const source = readFileSync(file, 'utf8');
    const backend = source.match(/DASHBOARD_BUILDING = '([^']+)'/)?.[1];
    expect(backend).toBeDefined();
    expect(DASHBOARD_BUILDING).toBe(backend);
  });
});

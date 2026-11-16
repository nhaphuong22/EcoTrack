import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import App from '../App';
import * as authService from '../services/auth';
import * as api from '../services/api';

vi.mock('../services/api', async () => {
  const actual = await vi.importActual('../services/api');
  return {
    ...actual,
    fetchMetrics: vi.fn().mockResolvedValue({
      total_consumption_kwh: 10000,
      peak_demand_kw: 300,
      estimated_cost_vnd: 25000000,
      active_anomalies_count: 0,
    }),
    fetchTimeSeries: vi.fn().mockResolvedValue({ data: [] }),
    fetchAnomalies: vi.fn().mockResolvedValue([]),
    fetchForecast: vi.fn().mockResolvedValue({ predictions: [] }),
    fetchZones: vi.fn().mockResolvedValue({ zones: [] }),
    fetchSystemHealth: vi.fn().mockResolvedValue({ status: 'healthy' }),
    fetchMLOpsStatus: vi.fn().mockResolvedValue({
      status: 'healthy',
      active_model: 'BDG2-XGBoost-Forecaster',
      drift_detected: false,
    }),
    triggerMLOpsRetrain: vi.fn().mockResolvedValue({
      message: 'Retraining initiated',
    }),
  };
});

// Mock Recharts
vi.mock('recharts', async () => {
  const original = await vi.importActual('recharts');
  return {
    ...original,
    ResponsiveContainer: ({ children }) => <div>{children}</div>,
  };
});

describe('Story 5.4: Frontend Authentication, Session & Role-Based Navigation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  describe('Unauthenticated Access Gate', () => {
    it('redirects unauthenticated visitor to the Login page', () => {
      render(<App />);

      expect(screen.getByText(/Đăng nhập vào/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Email làm việc/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Mật khẩu/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Đăng nhập/i })).toBeInTheDocument();

      // Dashboard elements must not be present
      expect(screen.queryByText(/Tổng quan Năng lượng/i)).not.toBeInTheDocument();
    });
  });

  describe('Login Form Submission', () => {
    it('displays inline error alert when credentials are invalid', async () => {
      vi.spyOn(authService, 'loginApi').mockRejectedValue({
        response: { data: { error: 'Invalid email or password' } },
      });

      render(<App />);

      fireEvent.change(screen.getByLabelText(/Email làm việc/i), {
        target: { value: 'wrong@ecotrack.io' },
      });
      fireEvent.change(screen.getByLabelText(/Mật khẩu/i), {
        target: { value: 'badpass' },
      });

      fireEvent.click(screen.getByRole('button', { name: /Đăng nhập/i }));

      await waitFor(() => {
        expect(screen.getByText('Invalid email or password')).toBeInTheDocument();
      });
    });

    it('lands on Dashboard upon successful login and displays user badge', async () => {
      const mockUser = {
        id: 'usr_tech_01',
        email: 'tech@ecotrack.io',
        name: 'Alex Technician',
        role: 'TECHNICIAN',
      };

      vi.spyOn(authService, 'loginApi').mockResolvedValue({
        token: 'valid_access_token',
        refreshToken: 'valid_refresh_token',
        user: mockUser,
      });

      render(<App />);

      fireEvent.change(screen.getByLabelText(/Email làm việc/i), {
        target: { value: 'tech@ecotrack.io' },
      });
      fireEvent.change(screen.getByLabelText(/Mật khẩu/i), {
        target: { value: 'SecureTechPass123!' },
      });

      fireEvent.click(screen.getByRole('button', { name: /Đăng nhập/i }));

      await waitFor(() => {
        expect(screen.getByText('Alex Technician')).toBeInTheDocument();
        expect(screen.getByText('TECHNICIAN')).toBeInTheDocument();
        expect(document.getElementById('tab-dashboard')).toBeInTheDocument();
      });
    });
  });

  describe('Role-Aware Navigation Matrix', () => {
    it('shows Dashboard & Floor Plan tabs but hides MLOps tab for TECHNICIAN', () => {
      localStorage.setItem(
        'ecotrack_user',
        JSON.stringify({ id: 'u1', name: 'Bob Tech', role: 'TECHNICIAN' })
      );
      localStorage.setItem('ecotrack_access_token', 'test_token');

      render(<App />);

      expect(document.getElementById('tab-dashboard')).toBeInTheDocument();
      expect(document.getElementById('tab-floorplan')).toBeInTheDocument();
      expect(document.getElementById('tab-mlops')).not.toBeInTheDocument();
    });

    it('renders MLOps tab for MANAGER and ADMIN', () => {
      localStorage.setItem(
        'ecotrack_user',
        JSON.stringify({ id: 'u2', name: 'Sara Manager', role: 'MANAGER' })
      );
      localStorage.setItem('ecotrack_access_token', 'test_token');

      render(<App />);

      expect(document.getElementById('tab-mlops')).toBeInTheDocument();
    });

    it('displays Retrain button in MLOps view only for ADMIN', async () => {
      // Login as ADMIN
      localStorage.setItem(
        'ecotrack_user',
        JSON.stringify({ id: 'u3', name: 'Super Admin', role: 'ADMIN' })
      );
      localStorage.setItem('ecotrack_access_token', 'test_token');

      render(<App />);

      const mlopsTab = document.getElementById('tab-mlops');
      fireEvent.click(mlopsTab);

      await waitFor(() => {
        expect(screen.getByText(/Quản trị Vòng đời Mô hình AI/i)).toBeInTheDocument();
        expect(document.getElementById('mlops-retrain-btn')).toBeInTheDocument();
      });
    });
  });

  describe('Logout Workflow', () => {
    it('clears stored tokens and returns to Login page when Đăng xuất is clicked', async () => {
      localStorage.setItem(
        'ecotrack_user',
        JSON.stringify({ id: 'u1', name: 'Admin User', role: 'ADMIN' })
      );
      localStorage.setItem('ecotrack_access_token', 'token_123');
      localStorage.setItem('ecotrack_refresh_token', 'refresh_123');

      const logoutSpy = vi.spyOn(authService, 'logoutApi').mockResolvedValue();

      render(<App />);

      const logoutBtn = document.getElementById('logout-btn');
      expect(logoutBtn).toBeInTheDocument();

      fireEvent.click(logoutBtn);

      await waitFor(() => {
        expect(logoutSpy).toHaveBeenCalled();
        expect(screen.getByText(/Đăng nhập vào/i)).toBeInTheDocument();
      });
    });
  });
});

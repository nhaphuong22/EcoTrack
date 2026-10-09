import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import App from '../App';
import * as api from '../services/api';

vi.mock('../services/api', () => ({
  API_BASE_URL: 'http://localhost:5000',
  fetchMetrics: vi.fn(),
  fetchTimeSeries: vi.fn(),
  fetchAnomalies: vi.fn(),
  fetchForecast: vi.fn(),
  sendCopilotMessage: vi.fn(),
}));

// Mock recharts ResponsiveContainer to avoid jsdom layout warning
vi.mock('recharts', async () => {
  const original = await vi.importActual('recharts');
  return {
    ...original,
    ResponsiveContainer: ({ children }) => <div data-testid="recharts-container">{children}</div>,
  };
});

describe('App - Story 1.7 Copilot & Anomaly Context Integration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.fetchMetrics.mockResolvedValue({
      total_consumption_kwh: 12500,
      peak_demand_kw: 450,
      estimated_cost_vnd: 38750000,
      active_anomalies_count: 2,
    });
    api.fetchTimeSeries.mockResolvedValue({ data: [] });
    api.fetchForecast.mockResolvedValue({ predictions: [] });
    api.sendCopilotMessage.mockResolvedValue({
      reply: 'Chẩn đoán: Tải tăng đột biến tại tầng 3.',
      tools_used: [],
    });
  });

  it('AC1: clicking "Copilot" on an anomaly row sends prepared diagnostic prompt as first message and opens the drawer', async () => {
    api.fetchAnomalies.mockResolvedValue([
      {
        id: 'ANOM-101',
        timestamp: '2026-10-09T08:00:00Z',
        severity: 'Critical',
        subsystem: 'HVAC Chiller',
        delta_kwh: 55.4,
        anomaly_score: 0.92,
        estimated_waste_vnd: 171740,
        estimated_waste_usd: 7.15,
      },
    ]);

    render(<App />);

    // Wait for anomaly button to appear
    await waitFor(() => {
      expect(document.getElementById('ask-copilot-ANOM-101')).toBeInTheDocument();
    });

    // Drawer is closed initially
    expect(document.querySelector('.bg-black\\/40')).not.toBeInTheDocument();
    expect(document.querySelector('aside')).toHaveClass('translate-x-full');
    expect(document.querySelector('aside')).not.toHaveClass('translate-x-0');

    const askBtn = document.getElementById('ask-copilot-ANOM-101');
    fireEvent.click(askBtn);

    // Prompt sent
    await waitFor(() => {
      expect(api.sendCopilotMessage).toHaveBeenCalledTimes(1);
    });

    const [sentPrompt, buildingId] = api.sendCopilotMessage.mock.calls[0];
    expect(sentPrompt).toContain('ANOM-101');
    expect(sentPrompt).toContain('2026-10-09T08:00');
    expect(sentPrompt).toContain('+55.4 kWh');
    expect(sentPrompt).toContain('0.92');
    expect(buildingId).toBe('office_tower_01');

    // Drawer is opened (open-state-gated backdrop rendered and aside translated into view)
    expect(document.querySelector('.bg-black\\/40')).toBeInTheDocument();
    expect(document.querySelector('aside')).toHaveClass('translate-x-0');
    expect(document.querySelector('aside')).not.toHaveClass('translate-x-full');
    expect(screen.getByText(new RegExp('Phân tích sự cố ANOM-101', 'i'))).toBeInTheDocument();
  });

  it('AC2: clicking "Copilot" on a second anomaly appends to the same conversation without losing earlier messages', async () => {
    api.fetchAnomalies.mockResolvedValue([
      {
        id: 'ANOM-101',
        timestamp: '2026-10-09T08:00:00Z',
        severity: 'Critical',
        subsystem: 'HVAC Chiller',
        delta_kwh: 55.4,
        anomaly_score: 0.92,
        estimated_waste_vnd: 171740,
        estimated_waste_usd: 7.15,
      },
      {
        id: 'ANOM-102',
        timestamp: '2026-10-09T09:00:00Z',
        severity: 'Medium',
        subsystem: 'Lighting',
        delta_kwh: 18.2,
        anomaly_score: 0.65,
        estimated_waste_vnd: 56420,
        estimated_waste_usd: 2.35,
      },
    ]);

    render(<App />);

    // 1st click
    await waitFor(() => {
      expect(document.getElementById('ask-copilot-ANOM-101')).toBeInTheDocument();
    });
    fireEvent.click(document.getElementById('ask-copilot-ANOM-101'));

    await waitFor(() => {
      expect(api.sendCopilotMessage).toHaveBeenCalledTimes(1);
    });
    // Wait for 1st reply
    await screen.findByText('Chẩn đoán: Tải tăng đột biến tại tầng 3.');

    // 2nd click on different anomaly
    const btn2 = document.getElementById('ask-copilot-ANOM-102');
    expect(btn2).toBeInTheDocument();
    fireEvent.click(btn2);

    await waitFor(() => {
      expect(api.sendCopilotMessage).toHaveBeenCalledTimes(2);
    });

    const [secondPrompt] = api.sendCopilotMessage.mock.calls[1];
    expect(secondPrompt).toContain('ANOM-102');

    // Verify both user prompts are present in the conversation
    expect(screen.getByText(new RegExp('Phân tích sự cố ANOM-101', 'i'))).toBeInTheDocument();
    expect(screen.getByText(new RegExp('Phân tích sự cố ANOM-102', 'i'))).toBeInTheDocument();
  });

  it('AC3: dashboard error banner names configured VITE_API_URL instead of hardcoded :8000', async () => {
    api.fetchMetrics.mockRejectedValue(new Error('Connection refused'));
    api.fetchTimeSeries.mockResolvedValue({ data: [] });
    api.fetchAnomalies.mockResolvedValue([]);

    render(<App />);

    const banner = await screen.findByText(/Không thể tải dữ liệu từ backend/i);
    expect(banner).toBeInTheDocument();

    // Must name configured URL (http://localhost:5000), NOT :8000
    expect(screen.getByText('http://localhost:5000')).toBeInTheDocument();
    expect(screen.queryByText('http://localhost:8000')).not.toBeInTheDocument();
  });

  it('floating Copilot button opens drawer without auto-sending any message', async () => {
    api.fetchAnomalies.mockResolvedValue([]);

    render(<App />);

    await waitFor(() => {
      expect(document.getElementById('floating-copilot-btn')).toBeInTheDocument();
    });

    // Drawer is closed initially
    expect(document.querySelector('.bg-black\\/40')).not.toBeInTheDocument();
    expect(document.querySelector('aside')).toHaveClass('translate-x-full');
    expect(document.querySelector('aside')).not.toHaveClass('translate-x-0');

    const floatingBtn = document.getElementById('floating-copilot-btn');
    fireEvent.click(floatingBtn);

    // Drawer opens (backdrop rendered, translate-x-0 applied)
    expect(document.querySelector('.bg-black\\/40')).toBeInTheDocument();
    expect(document.querySelector('aside')).toHaveClass('translate-x-0');
    expect(document.querySelector('aside')).not.toHaveClass('translate-x-full');
    // No message was sent
    expect(api.sendCopilotMessage).not.toHaveBeenCalled();
    // Welcome message is visible
    expect(screen.getByText(/trợ lý năng lượng thông minh/i)).toBeInTheDocument();
  });

  it('manual input in drawer sends to shared conversation', async () => {
    api.fetchAnomalies.mockResolvedValue([]);

    render(<App />);

    await waitFor(() => {
      expect(document.getElementById('floating-copilot-btn')).toBeInTheDocument();
    });
    fireEvent.click(document.getElementById('floating-copilot-btn'));

    const input = document.getElementById('copilot-input');
    fireEvent.change(input, { target: { value: 'Tại sao phụ tải tăng cao?' } });
    fireEvent.click(document.getElementById('copilot-send-btn'));

    await waitFor(() => {
      expect(api.sendCopilotMessage).toHaveBeenCalledWith(
        'Tại sao phụ tải tăng cao?',
        'office_tower_01',
        []
      );
    });
    expect(screen.getByText('Tại sao phụ tải tăng cao?')).toBeInTheDocument();
  });

  it('clear history resets conversation to welcome message', async () => {
    api.fetchAnomalies.mockResolvedValue([]);

    render(<App />);

    await waitFor(() => {
      expect(document.getElementById('floating-copilot-btn')).toBeInTheDocument();
    });
    fireEvent.click(document.getElementById('floating-copilot-btn'));

    const clearBtn = document.getElementById('copilot-clear-btn');
    fireEvent.click(clearBtn);

    expect(screen.getByText(/Đã xóa lịch sử hội thoại/i)).toBeInTheDocument();
  });

  it('handles Copilot API error and displays error message in drawer', async () => {
    api.sendCopilotMessage.mockRejectedValue(new Error('Gateway timeout'));
    api.fetchAnomalies.mockResolvedValue([]);

    render(<App />);

    await waitFor(() => {
      expect(document.getElementById('floating-copilot-btn')).toBeInTheDocument();
    });
    fireEvent.click(document.getElementById('floating-copilot-btn'));

    const input = document.getElementById('copilot-input');
    fireEvent.change(input, { target: { value: 'Kiểm tra hệ thống' } });
    fireEvent.click(document.getElementById('copilot-send-btn'));

    await waitFor(() => {
      expect(screen.getByText(/Không thể kết nối đến Copilot. Vui lòng thử lại./i)).toBeInTheDocument();
    });
    // Sent message is still preserved in history
    expect(screen.getByText('Kiểm tra hệ thống')).toBeInTheDocument();
  });
});

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import FloorPlan from '../components/dashboard/FloorPlan';
import * as api from '../services/api';

vi.mock('../services/api', () => ({
  API_BASE_URL: 'http://localhost:5000',
  fetchZones: vi.fn(),
}));

class MockEventSource {
  static instances = [];
  constructor(url) {
    this.url = url;
    this.listeners = {};
    MockEventSource.instances.push(this);
    setTimeout(() => {
      if (this.onopen) this.onopen();
    }, 10);
  }
  addEventListener(event, cb) {
    if (!this.listeners[event]) this.listeners[event] = [];
    this.listeners[event].push(cb);
  }
  emit(event, data) {
    if (this.listeners[event]) {
      this.listeners[event].forEach((cb) => cb({ data: JSON.stringify(data) }));
    }
  }
  close() {
    this.closed = true;
  }
}

describe('FloorPlan - Story 2.2 Live Floor Plan & Copilot Integration', () => {
  const mockZones = [
    {
      id: 'z1',
      name: 'Phòng 101',
      floor: 1,
      latest_reading: {
        outdoor_temperature_c: 24.2,
        meter_reading_kwh: 35.5,
        relative_humidity_pct: 60,
        timestamp: '2026-10-22T08:00:00Z',
      },
    },
    {
      id: 'z2',
      name: 'Phòng 102',
      floor: 1,
      latest_reading: {
        outdoor_temperature_c: 29.5,
        meter_reading_kwh: 88.0,
        relative_humidity_pct: 72,
        timestamp: '2026-10-22T08:00:00Z',
      },
    },
    {
      id: 'z3',
      name: 'Phòng 103',
      floor: 1,
      latest_reading: {
        outdoor_temperature_c: 21.0,
        meter_reading_kwh: 25.0,
        relative_humidity_pct: 55,
        timestamp: '2026-10-22T08:00:00Z',
      },
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    MockEventSource.instances = [];
    global.EventSource = MockEventSource;
    api.fetchZones.mockResolvedValue({
      building_id: 'office_tower_01',
      total: 3,
      zones: mockZones,
    });
  });

  afterEach(() => {
    delete global.EventSource;
  });

  it('AC1: fetches zones on mount and renders interactive SVG rooms with labels', async () => {
    render(<FloorPlan buildingId="office_tower_01" />);

    expect(api.fetchZones).toHaveBeenCalledWith('office_tower_01');

    // Wait for zones to load
    await waitFor(() => {
      expect(screen.getByText('Phòng 101')).toBeInTheDocument();
      expect(screen.getByText('Phòng 102')).toBeInTheDocument();
      expect(screen.getByText('Phòng 103')).toBeInTheDocument();
    });

    // Check SVG canvas
    const svg = screen.getByRole('img', { name: /Sơ đồ mặt bằng toà nhà Tầng 1/i });
    expect(svg).toBeInTheDocument();
  });

  it('AC2: toggles metric mode between "Nhiệt độ" and "Lãng phí" dynamically', async () => {
    render(<FloorPlan buildingId="office_tower_01" />);

    await waitFor(() => {
      expect(screen.getByText('24.2°C')).toBeInTheDocument();
      expect(screen.getByText('29.5°C')).toBeInTheDocument();
    });

    // Switch to "Lãng phí"
    const wasteBtn = document.getElementById('mode-toggle-waste');
    fireEvent.click(wasteBtn);

    // Display updates to kWh
    await waitFor(() => {
      expect(screen.getByText('35.5 kWh')).toBeInTheDocument();
      expect(screen.getByText('88.0 kWh')).toBeInTheDocument();
      expect(screen.getByText('Lãng phí cao')).toBeInTheDocument(); // For z2 > 80 kWh
    });

    // Switch back to "Nhiệt độ"
    const tempBtn = document.getElementById('mode-toggle-temp');
    fireEvent.click(tempBtn);

    await waitFor(() => {
      expect(screen.getByText('24.2°C')).toBeInTheDocument();
      expect(screen.getByText('Tối ưu')).toBeInTheDocument(); // For z1: 22-25°C
      expect(screen.getByText('Nhiệt cao')).toBeInTheDocument(); // For z2 > 28°C
    });
  });

  it('AC3: handles live SSE reading updates in real-time', async () => {
    render(<FloorPlan buildingId="office_tower_01" />);

    await waitFor(() => {
      expect(screen.getByText('24.2°C')).toBeInTheDocument();
    });

    // Verify EventSource connection
    expect(MockEventSource.instances.length).toBeGreaterThan(0);
    const es = MockEventSource.instances[0];

    // Simulate incoming SSE event for z1
    act(() => {
      es.emit('reading', {
        zone_id: 'z1',
        outdoor_temperature_c: 27.8,
        meter_reading_kwh: 92.4,
        relative_humidity_pct: 65,
        timestamp: '2026-10-22T08:05:00Z',
      });
    });

    // Temperature changes without reload
    await waitFor(() => {
      expect(screen.getByText('27.8°C')).toBeInTheDocument();
      expect(screen.getByText('Hơi ấm')).toBeInTheDocument();
    });
  });

  it('AC4: clicking or pressing Enter on a zone opens ZoneDetailModal and triggers Hỏi Copilot', async () => {
    const handleAskCopilot = vi.fn();
    render(<FloorPlan buildingId="office_tower_01" onAskCopilot={handleAskCopilot} />);

    await waitFor(() => {
      expect(screen.getByText('Phòng 102')).toBeInTheDocument();
    });

    // Find zone element for z2
    const roomElements = screen.getAllByRole('button');
    const z2Room = roomElements.find((el) => el.getAttribute('aria-label')?.includes('Phòng 102'));
    expect(z2Room).toBeDefined();

    // Trigger Enter key
    fireEvent.keyDown(z2Room, { key: 'Enter' });

    // Modal opens
    const modalTitle = await screen.findByRole('heading', { name: 'Phòng 102' });
    expect(modalTitle).toBeInTheDocument();
    expect(screen.getByText('88.0 kWh')).toBeInTheDocument();
    expect(screen.getAllByText('29.5°C').length).toBeGreaterThanOrEqual(2);

    // Click "Hỏi Copilot phân tích phòng này"
    const askCopilotBtn = document.getElementById('zone-ask-copilot-btn');
    expect(askCopilotBtn).toBeInTheDocument();
    fireEvent.click(askCopilotBtn);

    // Modal closes & onAskCopilot is triggered with zone object
    expect(handleAskCopilot).toHaveBeenCalledTimes(1);
    const calledZone = handleAskCopilot.mock.calls[0][0];
    expect(calledZone.id).toBe('z2');
    expect(calledZone.latest_reading.meter_reading_kwh).toBe(88.0);
  });

  it('AC5: shows live connection status badge', async () => {
    render(<FloorPlan buildingId="office_tower_01" />);

    await waitFor(() => {
      const badge = document.getElementById('stream-connection-badge');
      expect(badge).toBeInTheDocument();
      expect(badge).toHaveTextContent('Trực tuyến');
    });
  });
});

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import MonthlyReport from '../components/reports/MonthlyReport';
import { fetchMonthlyReport } from '../services/api';
import { exportMonthlyCsv, exportMonthlyPdf } from '../lib/reportExport';

vi.mock('../services/api', () => ({ fetchMonthlyReport: vi.fn() }));
vi.mock('../lib/reportExport', () => ({ exportMonthlyCsv: vi.fn(), exportMonthlyPdf: vi.fn() }));

const report = {
  report_id: 'office_tower_01-2026-11',
  generated_at: '2026-11-24T00:00:00.000Z',
  month: '2026-11',
  building: { id: 'office_tower_01', name: 'EcoTrack Tower' },
  summary: {
    total_consumption_kwh: 300,
    average_daily_kwh: 150,
    peak_demand_kw: 120,
    reading_count: 3,
    change_vs_previous_month_pct: -8.5,
    anomaly_count: 1,
    estimated_waste_vnd: 150000,
  },
  anomaly_breakdown: { CRITICAL: 1 },
  daily: [
    { date: '2026-11-01', consumption_kwh: 220, peak_demand_kw: 120, readings: 2 },
    { date: '2026-11-02', consumption_kwh: 80, peak_demand_kw: 80, readings: 1 },
  ],
};

describe('MonthlyReport', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    fetchMonthlyReport.mockResolvedValue(report);
  });

  it('renders monthly KPIs and exports the loaded report', async () => {
    render(<MonthlyReport />);
    expect(await screen.findByText('300 kWh')).toBeInTheDocument();
    expect(screen.getByText('8.5% tiết kiệm hơn tháng trước')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'CSV' }));
    fireEvent.click(screen.getByRole('button', { name: 'Xuất PDF' }));

    await waitFor(() => {
      expect(exportMonthlyCsv).toHaveBeenCalledWith(report);
      expect(exportMonthlyPdf).toHaveBeenCalledWith(report);
    });
  });
});

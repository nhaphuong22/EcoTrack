import { useState, useCallback } from 'react';
import { Bot, AlertCircle, LayoutDashboard, Map, FileBarChart } from 'lucide-react';
import Header from './components/layout/Header';
import MetricCards from './components/dashboard/MetricCards';
import ForecastChart from './components/dashboard/ForecastChart';
import AnomalyTable from './components/dashboard/AnomalyTable';
import FloorPlan from './components/dashboard/FloorPlan';
import SystemStatus from './components/dashboard/SystemStatus';
import CopilotDrawer from './components/copilot/CopilotDrawer';
import { useEnergyData } from './hooks/useEnergyData';
import { useCopilot } from './hooks/useCopilot';
import { buildAnomalyPrompt, buildZonePrompt } from './lib/copilotPrompt';
import { API_BASE_URL } from './services/api';
import MonthlyReport from './components/reports/MonthlyReport';

export default function App() {
  const { metrics, timeSeries, anomalies, forecast, loading, error, refetch } = useEnergyData(168);
  const { messages, isLoading: copilotLoading, error: copilotError, sendMessage, stopStreaming, retry, clearHistory } = useCopilot();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [activeTab, setActiveTab] = useState('dashboard'); // 'dashboard' | 'floorplan' | 'reports'

  const handleAskCopilot = useCallback((anomaly) => {
    const prompt = buildAnomalyPrompt(anomaly);
    sendMessage(prompt);
    setDrawerOpen(true);
  }, [sendMessage]);

  const handleAskCopilotZone = useCallback((zone) => {
    const prompt = buildZonePrompt(zone);
    sendMessage(prompt);
    setDrawerOpen(true);
  }, [sendMessage]);

  const tabClass = (active) =>
    `-mb-px flex items-center gap-2 border-b-2 px-1 pb-3 text-sm font-semibold transition-colors ${
      active
        ? 'border-shell text-ink'
        : 'border-transparent text-muted hover:border-line-strong hover:text-ink'
    }`;

  return (
    <div className="min-h-screen bg-ground">
      <Header onRefresh={refetch} loading={loading}>
        <div role="tablist" aria-label="Khu vực làm việc" className="flex items-end gap-6">
          <button
            id="tab-dashboard"
            role="tab"
            aria-selected={activeTab === 'dashboard'}
            onClick={() => setActiveTab('dashboard')}
            className={tabClass(activeTab === 'dashboard')}
          >
            <LayoutDashboard size={16} aria-hidden="true" />
            <span>Tổng quan Năng lượng</span>
          </button>

          <button
            id="tab-reports"
            role="tab"
            aria-selected={activeTab === 'reports'}
            onClick={() => setActiveTab('reports')}
            className={tabClass(activeTab === 'reports')}
          >
            <FileBarChart size={16} aria-hidden="true" />
            <span>Báo cáo tháng</span>
          </button>

          <button
            id="tab-floorplan"
            role="tab"
            aria-selected={activeTab === 'floorplan'}
            onClick={() => setActiveTab('floorplan')}
            className={tabClass(activeTab === 'floorplan')}
          >
            <Map size={16} aria-hidden="true" />
            <span>Sơ đồ Mặt bằng 2D</span>
            <span className="chip chip-ok">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-ok" aria-hidden="true" />
              Live
            </span>
          </button>
        </div>
      </Header>

      <main className="mx-auto max-w-screen-2xl space-y-5 px-4 py-5 sm:px-6 lg:px-8">
        {/* Error banner */}
        {activeTab === 'dashboard' && error && (
          <div role="alert" className="flex items-start gap-3 rounded-md border border-crit/30 bg-crit-bg px-4 py-3 text-sm text-crit">
            <AlertCircle size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
            <span>
              Không thể tải dữ liệu từ backend ({error}).{' '}
              Hãy đảm bảo backend đang chạy tại <code className="font-mono text-xs">{API_BASE_URL}</code>.
            </span>
          </div>
        )}

        {activeTab === 'dashboard' ? (
          <>
            <MetricCards metrics={metrics} />

            <ForecastChart timeSeries={timeSeries} forecast={forecast} loading={loading} />

            <div className="grid items-start gap-5 lg:grid-cols-3">
              <div className="lg:col-span-2">
                <AnomalyTable
                  anomalies={anomalies}
                  loading={loading}
                  onAskCopilot={handleAskCopilot}
                />
              </div>

              {/* Real system status (Story 2.3, FR45) */}
              <SystemStatus />
            </div>
          </>
        ) : activeTab === 'floorplan' ? (
          <FloorPlan onAskCopilot={handleAskCopilotZone} />
        ) : (
          <MonthlyReport />
        )}
      </main>

      {/* Floating Copilot button */}
      <button
        id="floating-copilot-btn"
        onClick={() => setDrawerOpen(true)}
        className="btn btn-primary fixed bottom-6 right-6 z-20 gap-2.5 rounded-full px-5 py-3.5 shadow-[0_6px_20px_-6px_rgba(12,58,62,0.55)]"
        title="Mở EcoTrack Copilot"
      >
        <Bot size={18} aria-hidden="true" />
        <span>Copilot</span>
        {anomalies?.length > 0 && (
          <span className="num -mr-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-warn-fill px-1 text-[11px] font-bold text-ink">
            {Math.min(anomalies.length, 9)}
          </span>
        )}
      </button>

      {/* Copilot Slide-over Drawer */}
      <CopilotDrawer
        isOpen={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        messages={messages}
        isLoading={copilotLoading}
        error={copilotError}
        sendMessage={sendMessage}
        stopStreaming={stopStreaming}
        retry={retry}
        clearHistory={clearHistory}
      />
    </div>
  );
}

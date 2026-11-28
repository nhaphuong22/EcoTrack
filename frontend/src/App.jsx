import { useState, useCallback } from 'react';
import { Sparkles, AlertCircle, LayoutDashboard, Map, Cpu, ArrowRight, FileBarChart, FlaskConical } from 'lucide-react';
import MLOpsPanel from './components/dashboard/MLOpsPanel';
import { canViewMLOps } from './hooks/useMLOpsStatus';
import Sidebar from './components/layout/Sidebar';
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
import WhatIfPanel from './components/dashboard/WhatIfPanel';

export default function App({ user = null, onBackToPortal = null, onLogout = null }) {
  const showMLOps = canViewMLOps(user);
  const [timeRangeHours, setTimeRangeHours] = useState(168);
  const { metrics, timeSeries, anomalies, forecast, loading, error, lastUpdated, refetch } = useEnergyData(timeRangeHours);
  const { messages, isLoading: copilotLoading, error: copilotError, sendMessage, stopStreaming, retry, clearHistory } = useCopilot();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [activeTab, setActiveTab] = useState('dashboard'); // 'dashboard' | 'floorplan' | 'reports' | 'whatif' | 'mlops'

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

  const scrollToAnomalies = useCallback(() => {
    document.getElementById('anomaly-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, []);

  const tabClass = (active) =>
    `flex w-full items-center justify-between gap-2.5 rounded-xl px-3.5 py-2.5 text-sm font-semibold transition-colors ${
      active
        ? 'bg-shell text-white shadow-sm'
        : 'text-ink-2 hover:bg-sunken hover:text-ink'
    }`;

  const updatedLabel = lastUpdated
    ? lastUpdated.toLocaleTimeString('vi-VN', { hour12: false })
    : null;

  const headerMeta =
    activeTab === 'floorplan'
      ? {
          title: 'Mặt bằng 2D',
          badge: (
            <span className="chip chip-ok">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-ok" aria-hidden="true" />
              Trực tuyến
            </span>
          ),
        }
      : activeTab === 'reports'
      ? {
          title: 'Báo cáo tháng',
          badge: null,
        }
      : activeTab === 'whatif'
      ? {
          title: 'Mô phỏng What-if',
          badge: null,
        }
      : activeTab === 'mlops' && showMLOps
      ? {
          title: 'AI & Mô hình',
          badge: null,
        }
      : {
          title: 'Tổng quan Năng lượng',
          badge: (
            <span className="chip chip-ok">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-ok" aria-hidden="true" />
              Thời gian thực
            </span>
          ),
        };

  return (
    <div className="flex min-h-screen">
      <Sidebar
        user={user}
        onBackToPortal={onBackToPortal}
        onLogout={onLogout}
        mobileOpen={mobileNavOpen}
        onCloseMobile={() => setMobileNavOpen(false)}
      >
        <div role="tablist" aria-label="Khu vực làm việc" aria-orientation="vertical" className="space-y-1.5">
          <button
            id="tab-dashboard"
            role="tab"
            type="button"
            aria-selected={activeTab === 'dashboard'}
            onClick={() => setActiveTab('dashboard')}
            className={tabClass(activeTab === 'dashboard')}
          >
            <span className="flex items-center gap-2.5">
              <LayoutDashboard size={17} aria-hidden="true" />
              <span>Tổng quan</span>
            </span>
          </button>

          <button
            id="tab-reports"
            role="tab"
            type="button"
            aria-selected={activeTab === 'reports'}
            onClick={() => setActiveTab('reports')}
            className={tabClass(activeTab === 'reports')}
          >
            <span className="flex items-center gap-2.5">
              <FileBarChart size={17} aria-hidden="true" />
              <span>Báo cáo tháng</span>
            </span>
          </button>

          <button
            id="tab-whatif"
            role="tab"
            type="button"
            aria-selected={activeTab === 'whatif'}
            onClick={() => setActiveTab('whatif')}
            className={tabClass(activeTab === 'whatif')}
          >
            <span className="flex items-center gap-2.5">
              <FlaskConical size={17} aria-hidden="true" />
              <span>What-if</span>
            </span>
          </button>

          <button
            id="tab-floorplan"
            role="tab"
            type="button"
            aria-selected={activeTab === 'floorplan'}
            onClick={() => setActiveTab('floorplan')}
            className={tabClass(activeTab === 'floorplan')}
          >
            <span className="flex items-center gap-2.5">
              <Map size={17} aria-hidden="true" />
              <span>Mặt bằng 2D</span>
            </span>
            <span
              className={`h-2 w-2 rounded-full ${activeTab === 'floorplan' ? 'bg-[#6ee7b7]' : 'bg-ok'} animate-pulse`}
              aria-hidden="true"
            />
          </button>

          {showMLOps && (
            <button
              id="tab-mlops"
              role="tab"
              type="button"
              aria-selected={activeTab === 'mlops'}
              onClick={() => setActiveTab('mlops')}
              className={tabClass(activeTab === 'mlops')}
            >
              <span className="flex items-center gap-2.5">
                <Cpu size={17} aria-hidden="true" />
                <span>AI &amp; Mô hình</span>
              </span>
            </button>
          )}
        </div>
      </Sidebar>

      <div className="flex min-w-0 flex-1 flex-col">
        <Header
          title={headerMeta.title}
          badge={headerMeta.badge}
          updatedLabel={activeTab === 'dashboard' ? updatedLabel : null}
          onRefresh={refetch}
          loading={loading}
          timeRange={timeRangeHours}
          onTimeRangeChange={setTimeRangeHours}
          showTimeRange={activeTab === 'dashboard'}
          onOpenMobileNav={() => setMobileNavOpen(true)}
        />

        <main className="mx-auto w-full max-w-screen-2xl flex-1 space-y-5 px-4 py-6 pb-24 sm:px-6 lg:px-8">
          {/* Error banner */}
          {activeTab === 'dashboard' && error && (
            <div role="alert" className="flex items-start gap-3 rounded-2xl border border-crit/30 bg-crit-bg px-4 py-3 text-sm text-crit">
              <AlertCircle size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
              <span>
                Không thể tải dữ liệu từ máy chủ ({error}).{' '}
                Vui lòng kiểm tra kết nối tại <code className="font-mono text-xs">{API_BASE_URL}</code>.
              </span>
            </div>
          )}

          {activeTab === 'dashboard' ? (
            <>
              <MetricCards
                metrics={metrics}
                anomalies={anomalies}
                timeSeries={timeSeries}
                onViewAnomalies={scrollToAnomalies}
              />

              <ForecastChart
                timeSeries={timeSeries}
                forecast={forecast}
                windowHours={timeRangeHours}
                loading={loading && timeSeries.length === 0}
              />

              <div className="grid items-start gap-5 lg:grid-cols-3">
                <div className="lg:col-span-2">
                  <AnomalyTable
                    anomalies={anomalies}
                    loading={loading && anomalies.length === 0}
                    onAskCopilot={handleAskCopilot}
                  />
                </div>

                <SystemStatus />
              </div>
            </>
          ) : activeTab === 'reports' ? (
            <MonthlyReport />
          ) : activeTab === 'whatif' ? (
            <WhatIfPanel />
          ) : activeTab === 'mlops' && showMLOps ? (
            <MLOpsPanel isAdmin={user?.role === 'ADMIN'} />
          ) : (
            <FloorPlan onAskCopilot={handleAskCopilotZone} />
          )}
        </main>
      </div>

      {/* Floating Copilot button */}
      <button
        id="floating-copilot-btn"
        type="button"
        onClick={() => setDrawerOpen(true)}
        className="fixed bottom-5 right-5 z-20 flex items-center gap-3 rounded-2xl border border-line-strong bg-white px-4 py-2.5 text-left shadow-[0_12px_28px_-8px_rgba(12,58,62,0.28)] transition-all hover:-translate-y-0.5 hover:border-shell/40 hover:shadow-[0_16px_32px_-8px_rgba(12,58,62,0.34)]"
        title="Mở EcoTrack Copilot"
      >
        <span className="relative flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-shell text-white">
          <Sparkles size={17} aria-hidden="true" />
          {anomalies?.length > 0 && (
            <span className="num absolute -right-1.5 -top-1.5 flex h-5 min-w-5 items-center justify-center rounded-full bg-crit px-1 text-[10px] font-bold text-white ring-2 ring-white">
              {Math.min(anomalies.length, 9)}
            </span>
          )}
        </span>
        <span className="hidden sm:block">
          <span className="block text-xs font-bold text-ink">EcoTrack Copilot</span>
          <span className="block text-[11px] text-muted">
            {anomalies?.length > 0
              ? `Phân tích ${anomalies.length} sự cố bất thường`
              : 'Hỏi đáp về tiêu thụ điện'}
          </span>
        </span>
        <ArrowRight size={15} className="hidden text-muted sm:block" aria-hidden="true" />
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

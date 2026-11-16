import { useState, useCallback, useEffect } from 'react';
import { Bot, AlertCircle, LayoutDashboard, Map, Cpu } from 'lucide-react';
import Header from './components/layout/Header';
import MetricCards from './components/dashboard/MetricCards';
import ForecastChart from './components/dashboard/ForecastChart';
import AnomalyTable from './components/dashboard/AnomalyTable';
import FloorPlan from './components/dashboard/FloorPlan';
import SystemStatus from './components/dashboard/SystemStatus';
import MLOpsView from './components/dashboard/MLOpsView';
import CopilotDrawer from './components/copilot/CopilotDrawer';
import LoginPage from './components/auth/LoginPage';
import { useEnergyData } from './hooks/useEnergyData';
import { useCopilot } from './hooks/useCopilot';
import { buildAnomalyPrompt, buildZonePrompt } from './lib/copilotPrompt';
import { API_BASE_URL } from './services/api';
import { getStoredAuth, logoutApi } from './services/auth';

export default function App() {
  const [user, setUser] = useState(() => getStoredAuth().user);
  const [activeTab, setActiveTab] = useState('dashboard'); // 'dashboard' | 'floorplan' | 'mlops'
  const [drawerOpen, setDrawerOpen] = useState(false);

  // Energy & Copilot hooks run only when authenticated
  const { metrics, timeSeries, anomalies, loading, error, refetch } = useEnergyData(user ? 168 : 0);
  const {
    messages,
    isLoading: copilotLoading,
    error: copilotError,
    sendMessage,
    stopStreaming,
    retry,
    clearHistory,
  } = useCopilot();

  // Listen to silent refresh failure or external logout
  useEffect(() => {
    const handleLogoutEvent = () => setUser(null);
    window.addEventListener('auth:logout', handleLogoutEvent);
    return () => window.removeEventListener('auth:logout', handleLogoutEvent);
  }, []);

  // Ensure technician cannot stay on MLOps tab
  useEffect(() => {
    if (activeTab === 'mlops' && user?.role === 'TECHNICIAN') {
      setActiveTab('dashboard');
    }
  }, [activeTab, user]);

  const handleLoginSuccess = useCallback((loggedUser) => {
    setUser(loggedUser);
    setActiveTab('dashboard');
  }, []);

  const handleLogout = useCallback(async () => {
    const { refreshToken } = getStoredAuth();
    await logoutApi(refreshToken);
    setUser(null);
  }, []);

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

  // If not signed in, show Login view
  if (!user) {
    return <LoginPage onLoginSuccess={handleLoginSuccess} />;
  }

  const canAccessMLOps = user.role === 'ADMIN' || user.role === 'MANAGER';

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950">
      <Header
        onRefresh={refetch}
        loading={loading}
        user={user}
        onLogout={handleLogout}
      />

      <main className="mx-auto max-w-screen-2xl space-y-6 px-4 py-6 sm:px-6 lg:px-8">
        {/* Navigation Tabs */}
        <div className="flex items-center gap-2 border-b border-slate-800/80 pb-3">
          <button
            id="tab-dashboard"
            onClick={() => setActiveTab('dashboard')}
            className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold transition ${
              activeTab === 'dashboard'
                ? 'bg-slate-800 text-emerald-400 border border-slate-700 shadow-sm'
                : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'
            }`}
          >
            <LayoutDashboard size={16} />
            <span>Tổng quan Năng lượng</span>
          </button>

          <button
            id="tab-floorplan"
            onClick={() => setActiveTab('floorplan')}
            className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold transition ${
              activeTab === 'floorplan'
                ? 'bg-slate-800 text-emerald-400 border border-slate-700 shadow-sm'
                : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'
            }`}
          >
            <Map size={16} />
            <span>Sơ đồ Mặt bằng 2D</span>
            <span className="flex items-center gap-1 rounded-full bg-emerald-500/15 border border-emerald-500/30 px-2 py-0.5 text-[10px] font-bold text-emerald-400">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
              Live
            </span>
          </button>

          {/* MLOps Tab (Admin & Manager Only) */}
          {canAccessMLOps && (
            <button
              id="tab-mlops"
              onClick={() => setActiveTab('mlops')}
              className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold transition ${
                activeTab === 'mlops'
                  ? 'bg-slate-800 text-violet-400 border border-slate-700 shadow-sm'
                  : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'
              }`}
            >
              <Cpu size={16} />
              <span>Quản trị Mô hình & Drift</span>
              <span className="rounded bg-violet-500/15 border border-violet-500/30 px-1.5 py-0.2 text-[10px] font-semibold text-violet-400">
                MLOps
              </span>
            </button>
          )}
        </div>

        {/* Error banner */}
        {error && (
          <div className="flex items-center gap-3 rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-400">
            <AlertCircle size={16} />
            <span>
              Không thể tải dữ liệu từ backend ({error}).{' '}
              Hãy đảm bảo backend đang chạy tại <code className="font-mono text-xs">{API_BASE_URL}</code>.
            </span>
          </div>
        )}

        {/* View based on activeTab */}
        {activeTab === 'dashboard' && (
          <>
            {/* KPI Metric Cards */}
            <MetricCards metrics={metrics} />

            {/* Time-series forecast chart */}
            <ForecastChart timeSeries={timeSeries} loading={loading} />

            {/* Bottom: Anomaly triage board */}
            <div className="grid gap-6 lg:grid-cols-3">
              <div className="lg:col-span-2">
                <AnomalyTable
                  anomalies={anomalies}
                  loading={loading}
                  onAskCopilot={handleAskCopilot}
                />
              </div>

              {/* Right: Real System status (Story 2.3, FR45) */}
              <SystemStatus />
            </div>
          </>
        )}

        {activeTab === 'floorplan' && (
          <FloorPlan onAskCopilot={handleAskCopilotZone} />
        )}

        {activeTab === 'mlops' && canAccessMLOps && (
          <MLOpsView user={user} />
        )}
      </main>

      {/* Floating Copilot button */}
      <button
        id="floating-copilot-btn"
        onClick={() => setDrawerOpen(true)}
        className="fixed bottom-7 right-7 flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-br from-sky-500 to-violet-600 shadow-2xl shadow-sky-500/30 transition hover:scale-105 hover:shadow-sky-500/50 active:scale-95 z-20"
        title="Mở EcoTrack Copilot"
      >
        <Bot size={24} className="text-white" />
        {anomalies?.length > 0 && (
          <span className="absolute -right-1 -top-1 flex h-5 w-5 items-center justify-center rounded-full bg-rose-500 text-[10px] font-bold text-white">
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

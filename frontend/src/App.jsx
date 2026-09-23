import { useState, useCallback } from 'react';
import { Bot, AlertCircle } from 'lucide-react';
import Header from './components/layout/Header';
import MetricCards from './components/dashboard/MetricCards';
import ForecastChart from './components/dashboard/ForecastChart';
import AnomalyTable from './components/dashboard/AnomalyTable';
import CopilotDrawer from './components/copilot/CopilotDrawer';
import { useEnergyData } from './hooks/useEnergyData';

export default function App() {
  const { metrics, timeSeries, anomalies, loading, error, refetch } = useEnergyData(168);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [pendingPrompt, setPendingPrompt] = useState('');

  const handleAskCopilot = useCallback((anomaly) => {
    setPendingPrompt(
      `Phân tích sự cố ${anomaly.id} xảy ra lúc ${anomaly.timestamp?.slice(0, 16)} — ` +
      `phụ tải tăng +${anomaly.delta_kwh} kWh so với baseline, điểm bất thường ${anomaly.anomaly_score?.toFixed(2)}. ` +
      `Chẩn đoán nguyên nhân và đề xuất hành động xử lý.`
    );
    setDrawerOpen(true);
  }, []);

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950">
      <Header onRefresh={refetch} loading={loading} />

      <main className="mx-auto max-w-screen-2xl space-y-6 px-4 py-6 sm:px-6 lg:px-8">
        {/* Error banner */}
        {error && (
          <div className="flex items-center gap-3 rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-400">
            <AlertCircle size={16} />
            <span>
              Không thể tải dữ liệu từ backend ({error}).{' '}
              Hãy đảm bảo backend đang chạy tại <code className="font-mono text-xs">http://localhost:8000</code>.
            </span>
          </div>
        )}

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

          {/* Right: System status */}
          <div className="rounded-2xl border border-slate-700 bg-slate-800/60 p-5 space-y-4 backdrop-blur-sm">
            <h3 className="font-semibold text-white">Trạng thái hệ thống</h3>
            {[
              { label: 'XGBoost Forecaster', status: 'Đang chạy', ok: true },
              { label: 'Isolation Forest Detector', status: 'Đang chạy', ok: true },
              { label: 'LLM Copilot Agent', status: 'Sẵn sàng', ok: true },
              { label: 'Data Pipeline (BDG2)', status: 'Đồng bộ', ok: true },
            ].map(s => (
              <div key={s.label} className="flex items-center justify-between text-sm">
                <span className="text-slate-400">{s.label}</span>
                <span className={`flex items-center gap-1.5 font-medium ${s.ok ? 'text-emerald-400' : 'text-rose-400'}`}>
                  <span className={`h-2 w-2 rounded-full ${s.ok ? 'bg-emerald-400' : 'bg-rose-400'} animate-pulse`} />
                  {s.status}
                </span>
              </div>
            ))}
          </div>
        </div>
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
        onClose={() => { setDrawerOpen(false); setPendingPrompt(''); }}
        initialMessage={pendingPrompt}
      />
    </div>
  );
}

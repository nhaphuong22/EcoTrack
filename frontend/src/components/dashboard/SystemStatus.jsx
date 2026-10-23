import { Activity, RefreshCw } from 'lucide-react';
import { useSystemStatus } from '../../hooks/useSystemStatus';

export default function SystemStatus({ pollIntervalMs = 30000 }) {
  const { healthData, isUnknown, loading, refetch } = useSystemStatus(pollIntervalMs);

  // Compute live states dynamically without any hardcoding
  const getComponentStatus = (key) => {
    if (isUnknown) {
      return {
        text: 'Không xác định',
        state: 'unknown',
        colorClass: 'text-amber-400',
        dotClass: 'bg-amber-400',
      };
    }

    const services = healthData?.services || {};
    const models = healthData?.models || {};
    const copilotEngine = healthData?.copilot_engine;

    switch (key) {
      case 'xgboost': {
        const isOk = models.forecast === 'loaded';
        return {
          text: isOk ? 'Đang chạy' : 'Không khả dụng',
          state: isOk ? 'healthy' : 'unavailable',
          colorClass: isOk ? 'text-emerald-400' : 'text-rose-400',
          dotClass: isOk ? 'bg-emerald-400' : 'bg-rose-400',
        };
      }
      case 'isolation_forest': {
        const isOk = models.anomaly === 'loaded';
        return {
          text: isOk ? 'Đang chạy' : 'Không khả dụng',
          state: isOk ? 'healthy' : 'unavailable',
          colorClass: isOk ? 'text-emerald-400' : 'text-rose-400',
          dotClass: isOk ? 'bg-emerald-400' : 'bg-rose-400',
        };
      }
      case 'copilot': {
        const isOk = copilotEngine && copilotEngine !== 'unavailable';
        return {
          text: isOk ? `Sẵn sàng (${copilotEngine})` : 'Không khả dụng',
          state: isOk ? 'healthy' : 'unavailable',
          colorClass: isOk ? 'text-emerald-400' : 'text-rose-400',
          dotClass: isOk ? 'bg-emerald-400' : 'bg-rose-400',
        };
      }
      case 'database': {
        const isOk = services.database === 'connected';
        return {
          text: isOk ? 'Đồng bộ' : 'Mất kết nối',
          state: isOk ? 'healthy' : 'unavailable',
          colorClass: isOk ? 'text-emerald-400' : 'text-rose-400',
          dotClass: isOk ? 'bg-emerald-400' : 'bg-rose-400',
        };
      }
      case 'ai_service': {
        const isOk = services.ai_service === 'connected';
        return {
          text: isOk ? 'Trực tuyến' : 'Ngoại tuyến',
          state: isOk ? 'healthy' : 'unavailable',
          colorClass: isOk ? 'text-emerald-400' : 'text-rose-400',
          dotClass: isOk ? 'bg-emerald-400' : 'bg-rose-400',
        };
      }
      default:
        return {
          text: 'Không xác định',
          state: 'unknown',
          colorClass: 'text-slate-400',
          dotClass: 'bg-slate-400',
        };
    }
  };

  const components = [
    { id: 'status-xgboost', key: 'xgboost', label: 'XGBoost Forecaster' },
    { id: 'status-isolation-forest', key: 'isolation_forest', label: 'Isolation Forest Detector' },
    { id: 'status-copilot', key: 'copilot', label: 'LLM Copilot Agent' },
    { id: 'status-database', key: 'database', label: 'PostgreSQL Database' },
    { id: 'status-ai-service', key: 'ai_service', label: 'FastAPI AI Engine' },
  ];

  return (
    <div
      id="system-status-panel"
      className="rounded-2xl border border-slate-700 bg-slate-800/60 p-5 space-y-4 backdrop-blur-sm shadow-xl"
    >
      <div className="flex items-center justify-between border-b border-slate-700/60 pb-3">
        <div className="flex items-center gap-2">
          <Activity size={16} className="text-emerald-400" />
          <h3 className="font-semibold text-white">Trạng thái hệ thống</h3>
        </div>
        <button
          onClick={refetch}
          disabled={loading}
          className="text-slate-400 hover:text-white transition p-1 rounded-md"
          title="Làm mới trạng thái"
          aria-label="Làm mới trạng thái hệ thống"
        >
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      <div className="space-y-3">
        {components.map((c) => {
          const status = getComponentStatus(c.key);
          return (
            <div
              key={c.key}
              id={c.id}
              className="flex items-center justify-between text-sm py-0.5"
            >
              <span className="text-slate-400 font-normal">{c.label}</span>
              <span className={`flex items-center gap-1.5 font-medium ${status.colorClass}`}>
                <span
                  className={`h-2 w-2 rounded-full ${status.dotClass} ${
                    status.state === 'healthy' ? 'animate-pulse' : ''
                  }`}
                />
                <span data-testid={`${c.key}-status-text`}>{status.text}</span>
              </span>
            </div>
          );
        })}
      </div>

      <div className="pt-2 border-t border-slate-800 text-[11px] text-slate-500 flex items-center justify-between">
        <span>Chu kỳ kiểm tra: 30s</span>
        <span className="font-mono">
          {healthData?.timestamp
            ? new Date(healthData.timestamp).toLocaleTimeString('vi-VN')
            : isUnknown
            ? 'Mất kết nối'
            : 'Đang tải...'}
        </span>
      </div>
    </div>
  );
}

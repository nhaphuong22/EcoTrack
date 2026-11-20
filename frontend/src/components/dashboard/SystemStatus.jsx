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
        colorClass: 'text-warn',
        dotClass: 'bg-warn-fill',
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
          colorClass: isOk ? 'text-ok' : 'text-crit',
          dotClass: isOk ? 'bg-ok' : 'bg-crit',
        };
      }
      case 'isolation_forest': {
        const isOk = models.anomaly === 'loaded';
        return {
          text: isOk ? 'Đang chạy' : 'Không khả dụng',
          state: isOk ? 'healthy' : 'unavailable',
          colorClass: isOk ? 'text-ok' : 'text-crit',
          dotClass: isOk ? 'bg-ok' : 'bg-crit',
        };
      }
      case 'copilot': {
        const isOk = copilotEngine && copilotEngine !== 'unavailable';
        return {
          text: isOk ? `Sẵn sàng (${copilotEngine})` : 'Không khả dụng',
          state: isOk ? 'healthy' : 'unavailable',
          colorClass: isOk ? 'text-ok' : 'text-crit',
          dotClass: isOk ? 'bg-ok' : 'bg-crit',
        };
      }
      case 'database': {
        const isOk = services.database === 'connected';
        return {
          text: isOk ? 'Đồng bộ' : 'Mất kết nối',
          state: isOk ? 'healthy' : 'unavailable',
          colorClass: isOk ? 'text-ok' : 'text-crit',
          dotClass: isOk ? 'bg-ok' : 'bg-crit',
        };
      }
      case 'ai_service': {
        const isOk = services.ai_service === 'connected';
        return {
          text: isOk ? 'Trực tuyến' : 'Ngoại tuyến',
          state: isOk ? 'healthy' : 'unavailable',
          colorClass: isOk ? 'text-ok' : 'text-crit',
          dotClass: isOk ? 'bg-ok' : 'bg-crit',
        };
      }
      default:
        return {
          text: 'Không xác định',
          state: 'unknown',
          colorClass: 'text-muted',
          dotClass: 'bg-faint',
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
    <section id="system-status-panel" className="panel" aria-label="Trạng thái hệ thống">
      <div className="panel-head">
        <div className="flex items-center gap-2">
          <Activity size={16} className="text-muted" aria-hidden="true" />
          <h3 className="panel-title">Trạng thái hệ thống</h3>
        </div>
        <button
          onClick={refetch}
          disabled={loading}
          className="btn btn-quiet btn-sm px-2"
          title="Làm mới trạng thái"
          aria-label="Làm mới trạng thái hệ thống"
        >
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} aria-hidden="true" />
        </button>
      </div>

      <ul className="divide-y divide-line">
        {components.map((c) => {
          const status = getComponentStatus(c.key);
          return (
            <li
              key={c.key}
              id={c.id}
              className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm"
            >
              <span className="text-ink-2">{c.label}</span>
              <span className={`flex items-center gap-2 font-semibold ${status.colorClass}`}>
                <span className={`h-2 w-2 rounded-full ${status.dotClass}`} aria-hidden="true" />
                <span data-testid={`${c.key}-status-text`}>{status.text}</span>
              </span>
            </li>
          );
        })}
      </ul>

      <div className="flex items-center justify-between border-t border-line px-4 py-2.5 text-xs text-muted">
        <span>Chu kỳ kiểm tra: 30s</span>
        <span className="num">
          {healthData?.timestamp
            ? new Date(healthData.timestamp).toLocaleTimeString('vi-VN')
            : isUnknown
            ? 'Mất kết nối'
            : 'Đang tải...'}
        </span>
      </div>
    </section>
  );
}

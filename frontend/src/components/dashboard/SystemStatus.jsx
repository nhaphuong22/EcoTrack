import { RefreshCw } from 'lucide-react';
import { useSystemStatus } from '../../hooks/useSystemStatus';

export default function SystemStatus({ pollIntervalMs = 30000 }) {
  const { healthData, isUnknown, loading, refetch } = useSystemStatus(pollIntervalMs);

  // Compute live states dynamically without any hardcoding
  const getComponentStatus = (key) => {
    if (isUnknown) {
      return {
        text: 'Không xác định',
        state: 'unknown',
        chipClass: 'chip-warn',
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
          chipClass: isOk ? 'chip-ok' : 'chip-crit',
          dotClass: isOk ? 'bg-ok' : 'bg-crit',
        };
      }
      case 'isolation_forest': {
        const isOk = models.anomaly === 'loaded';
        return {
          text: isOk ? 'Đang chạy' : 'Không khả dụng',
          state: isOk ? 'healthy' : 'unavailable',
          chipClass: isOk ? 'chip-ok' : 'chip-crit',
          dotClass: isOk ? 'bg-ok' : 'bg-crit',
        };
      }
      case 'copilot': {
        const isOk = copilotEngine && copilotEngine !== 'unavailable';
        return {
          text: isOk ? 'Sẵn sàng' : 'Không khả dụng',
          state: isOk ? 'healthy' : 'unavailable',
          chipClass: isOk ? 'chip-ok' : 'chip-crit',
          dotClass: isOk ? 'bg-ok' : 'bg-crit',
        };
      }
      case 'database': {
        const isOk = services.database === 'connected';
        return {
          text: isOk ? 'Đồng bộ' : 'Mất kết nối',
          state: isOk ? 'healthy' : 'unavailable',
          chipClass: isOk ? 'chip-ok' : 'chip-crit',
          dotClass: isOk ? 'bg-ok' : 'bg-crit',
        };
      }
      case 'ai_service': {
        const isOk = services.ai_service === 'connected';
        return {
          text: isOk ? 'Trực tuyến' : 'Ngoại tuyến',
          state: isOk ? 'healthy' : 'unavailable',
          chipClass: isOk ? 'chip-ok' : 'chip-crit',
          dotClass: isOk ? 'bg-ok' : 'bg-crit',
        };
      }
      default:
        return {
          text: 'Không xác định',
          state: 'unknown',
          chipClass: 'chip-mute',
          dotClass: 'bg-faint',
        };
    }
  };

  const components = [
    {
      id: 'status-xgboost',
      key: 'xgboost',
      label: 'Dự báo nhu cầu điện',
      description: 'Ước tính phụ tải 24 giờ tới',
    },
    {
      id: 'status-isolation-forest',
      key: 'isolation_forest',
      label: 'Giám sát bất thường',
      description: 'Phát hiện tiêu thụ vượt mức',
    },
    {
      id: 'status-copilot',
      key: 'copilot',
      label: 'Trợ lý EcoTrack',
      description: 'Tư vấn và phân tích sự cố',
    },
    {
      id: 'status-database',
      key: 'database',
      label: 'Lưu trữ số liệu',
      description: 'Ghi nhận dữ liệu công tơ theo giờ',
    },
    {
      id: 'status-ai-service',
      key: 'ai_service',
      label: 'Trung tâm phân tích',
      description: 'Tổng hợp số liệu và cảnh báo',
    },
  ];

  const statuses = components.map((c) => ({ ...c, status: getComponentStatus(c.key) }));
  const allHealthy = !isUnknown && statuses.every((item) => item.status.state === 'healthy');

  const summaryBadge = isUnknown
    ? { text: 'Mất kết nối', cls: 'chip-warn', dot: 'bg-warn-fill' }
    : allHealthy
    ? { text: 'Hoạt động tốt', cls: 'chip-ok', dot: 'bg-ok' }
    : { text: 'Cần kiểm tra', cls: 'chip-crit', dot: 'bg-crit' };

  return (
    <section id="system-status-panel" className="panel" aria-label="Tình trạng vận hành">
      <div className="panel-head">
        <h3 className="panel-title">Tình trạng vận hành</h3>
        <div className="flex items-center gap-2">
          <span className={`chip ${summaryBadge.cls}`}>
            <span className={`h-1.5 w-1.5 rounded-full ${summaryBadge.dot}`} aria-hidden="true" />
            {summaryBadge.text}
          </span>
          <button
            type="button"
            onClick={refetch}
            disabled={loading}
            className="btn btn-quiet btn-sm px-2"
            title="Kiểm tra lại"
            aria-label="Kiểm tra lại tình trạng vận hành"
          >
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} aria-hidden="true" />
          </button>
        </div>
      </div>

      <ul className="space-y-2.5 p-4">
        {statuses.map((c) => (
          <li
            key={c.key}
            id={c.id}
            className="flex items-center justify-between gap-3 rounded-xl border border-line/80 bg-sunken/70 px-3.5 py-2.5"
          >
            <div className="min-w-0">
              <p className="flex items-center gap-2 text-sm font-semibold text-ink">
                <span className={`h-2 w-2 shrink-0 rounded-full ${c.status.dotClass}`} aria-hidden="true" />
                <span className="truncate">{c.label}</span>
              </p>
              <p className="mt-0.5 pl-4 text-xs text-muted">{c.description}</p>
            </div>
            <span
              data-testid={`${c.key}-status-text`}
              className={`chip shrink-0 ${c.status.chipClass}`}
            >
              {c.status.text}
            </span>
          </li>
        ))}
      </ul>

      <div className="flex items-center justify-between border-t border-line px-5 py-3 text-xs text-muted">
        <span>Tự động kiểm tra: 30 giây</span>
        <span className="num rounded-lg border border-line bg-sunken px-2 py-0.5 text-[11px] font-medium text-ink-2">
          {healthData?.timestamp
            ? new Date(healthData.timestamp).toLocaleTimeString('vi-VN', { hour12: false })
            : isUnknown
            ? 'Mất kết nối'
            : 'Đang tải...'}
        </span>
      </div>
    </section>
  );
}

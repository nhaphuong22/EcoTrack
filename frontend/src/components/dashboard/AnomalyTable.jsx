import { CheckCircle2, Download, Sparkles } from 'lucide-react';
import { format, parseISO } from 'date-fns';

function formatLocalTimestamp(iso) {
  if (!iso) return '—';
  try {
    return format(parseISO(iso), 'dd/MM HH:mm');
  } catch {
    return iso.slice(0, 16).replace('T', ' ');
  }
}

const SEVERITY_CONFIG = {
  Critical: { label: 'Nghiêm trọng', chip: 'chip-crit' },
  Medium: { label: 'Trung bình', chip: 'chip-warn' },
  Low: { label: 'Thấp', chip: 'chip-mute' },
  Normal: { label: 'Bình thường', chip: 'chip-ok' },
};

const STATUS_CONFIG = {
  OPEN: { label: 'Chưa xử lý', chip: 'chip-crit' },
  ACKNOWLEDGED: { label: 'Đã ghi nhận', chip: 'chip-warn' },
  RESOLVED: { label: 'Đã xử lý', chip: 'chip-ok' },
  IGNORED: { label: 'Đã bỏ qua', chip: 'chip-mute' },
};

function cleanDescription(text) {
  if (!text) return '';
  if (text === 'Abnormal load deviation exceeding baseline prediction') {
    return 'Tiêu thụ vượt mức dự báo bình thường';
  }
  return text;
}

function escapeCsvCell(value) {
  const str = String(value ?? '');
  if (/[",\n]/.test(str)) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

function exportAnomaliesCsv(anomalies) {
  const headers = ['Thời điểm', 'Hệ thống & Thiết bị', 'Mức độ', 'Chênh lệch (kWh)', 'Lãng phí (VNĐ)', 'Trạng thái', 'Mô tả'];
  const rows = anomalies.map((anom) => {
    const sevKey = String(anom.severity || 'Low');
    const sevLabel = (SEVERITY_CONFIG[sevKey.charAt(0).toUpperCase() + sevKey.slice(1).toLowerCase()] || SEVERITY_CONFIG.Low).label;
    const statusLabel = (STATUS_CONFIG[String(anom.status || 'OPEN').toUpperCase()] || STATUS_CONFIG.OPEN).label;
    return [
      formatLocalTimestamp(anom.timestamp),
      anom.subsystem || 'Hệ thống tòa nhà',
      sevLabel,
      anom.delta_kwh ?? '',
      anom.estimated_waste_vnd ?? '',
      statusLabel,
      cleanDescription(anom.description),
    ]
      .map(escapeCsvCell)
      .join(',');
  });

  if (typeof URL.createObjectURL !== 'function') return;
  const csvContent = '\uFEFF' + [headers.map(escapeCsvCell).join(','), ...rows].join('\n');
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'su-co-nang-luong.csv';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

export default function AnomalyTable({ anomalies, loading, onAskCopilot }) {
  if (loading) {
    return (
      <div className="panel space-y-px overflow-hidden bg-line" aria-busy="true">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="h-16 animate-pulse bg-panel" />
        ))}
      </div>
    );
  }

  if (!anomalies?.length) {
    return (
      <section id="anomaly-section" className="panel flex items-center gap-4 px-6 py-7" aria-label="Danh sách sự cố cần xử lý">
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-ok-bg text-ok">
          <CheckCircle2 size={24} aria-hidden="true" />
        </span>
        <div>
          <p className="text-sm font-semibold text-ink">Không phát hiện bất thường</p>
          <p className="meta mt-0.5">Hệ thống vận hành ổn định, chưa ghi nhận sự cố nào trong thời gian theo dõi.</p>
        </div>
      </section>
    );
  }

  return (
    <section id="anomaly-section" className="panel overflow-hidden" aria-label="Sự cố cần xử lý">
      <div className="panel-head">
        <div className="flex items-center gap-2.5">
          <h3 className="panel-title">Sự cố cần xử lý</h3>
          <span className="chip chip-crit num">{anomalies.length} sự cố</span>
        </div>
        <button
          type="button"
          onClick={() => exportAnomaliesCsv(anomalies)}
          className="btn btn-quiet btn-sm"
          title="Tải danh sách sự cố"
        >
          <Download size={13} aria-hidden="true" />
          <span>Xuất file</span>
        </button>
      </div>

      <div className="max-h-[360px] overflow-auto">
        <table className="w-full min-w-[640px] border-collapse text-left text-sm">
          <thead className="sticky top-0 z-10 border-b border-line bg-sunken/90 text-xs text-muted backdrop-blur-sm">
            <tr>
              <th scope="col" className="px-5 py-2.5 font-medium">Hệ thống &amp; Thiết bị</th>
              <th scope="col" className="px-3 py-2.5 font-medium">Thời điểm</th>
              <th scope="col" className="px-3 py-2.5 text-right font-medium">Chênh lệch</th>
              <th scope="col" className="px-3 py-2.5 text-right font-medium">Lãng phí</th>
              <th scope="col" className="px-3 py-2.5 font-medium">Trạng thái</th>
              <th scope="col" className="px-5 py-2.5 text-right font-medium">Thao tác</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {anomalies.map((anom) => {
              const severity = String(anom.severity || 'Low');
              const sevCfg =
                SEVERITY_CONFIG[severity.charAt(0).toUpperCase() + severity.slice(1).toLowerCase()] ||
                SEVERITY_CONFIG.Low;
              const statusKey = String(anom.status || 'OPEN').toUpperCase();
              const statusCfg = STATUS_CONFIG[statusKey] || STATUS_CONFIG.OPEN;
              const ts = formatLocalTimestamp(anom.timestamp);
              const desc = cleanDescription(anom.description);

              return (
                <tr key={anom.id} className="align-middle hover:bg-sunken/60">
                  <td className="px-5 py-3.5">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold text-ink">{anom.subsystem || 'Hệ thống tòa nhà'}</span>
                      <span className={`chip ${sevCfg.chip}`}>{sevCfg.label}</span>
                    </div>
                    {desc && (
                      <p className="mt-1 max-w-xs truncate text-xs text-muted">{desc}</p>
                    )}
                  </td>
                  <td className="whitespace-nowrap px-3 py-3.5">
                    <p className="num text-xs font-medium text-ink-2">{ts}</p>
                    {anom.outdoor_temp_c != null && (
                      <p className="num mt-0.5 text-[11px] text-muted">{anom.outdoor_temp_c}°C</p>
                    )}
                  </td>
                  <td className="num whitespace-nowrap px-3 py-3.5 text-right font-semibold text-crit">
                    {anom.delta_kwh == null ? '—' : `+${anom.delta_kwh} kWh`}
                  </td>
                  <td className="whitespace-nowrap px-3 py-3.5 text-right">
                    <p className="num font-semibold text-ink">
                      {anom.estimated_waste_vnd?.toLocaleString('vi-VN') ?? '—'} đ
                    </p>
                    {anom.estimated_waste_usd != null && (
                      <p className="num text-[11px] text-muted">≈ ${anom.estimated_waste_usd}</p>
                    )}
                  </td>
                  <td className="whitespace-nowrap px-3 py-3.5">
                    <span className={`chip ${statusCfg.chip}`}>{statusCfg.label}</span>
                  </td>
                  <td className="px-5 py-3.5 text-right">
                    <button
                      id={`ask-copilot-${anom.id}`}
                      type="button"
                      onClick={() => onAskCopilot?.(anom)}
                      className="btn btn-sm border border-shell/20 bg-ok-bg/60 text-shell hover:bg-ok-bg"
                      title="Hỏi Copilot về sự cố này"
                    >
                      <Sparkles size={13} aria-hidden="true" />
                      Copilot
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

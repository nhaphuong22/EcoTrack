import { CheckCircle2, MessageSquare } from 'lucide-react';

const SEVERITY_CONFIG = {
  Critical: { chip: 'chip-crit', row: 'bg-crit' },
  Medium:   { chip: 'chip-warn', row: 'bg-warn-fill' },
  Low:      { chip: 'chip-mute', row: 'bg-line-strong' },
  Normal:   { chip: 'chip-ok',   row: 'bg-ok' },
};

export default function AnomalyTable({ anomalies, loading, onAskCopilot }) {
  if (loading) {
    return (
      <div className="panel space-y-px overflow-hidden bg-line" aria-busy="true">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="h-14 animate-pulse bg-panel" />
        ))}
      </div>
    );
  }

  if (!anomalies?.length) {
    return (
      <div className="panel flex items-center gap-4 px-5 py-6">
        <CheckCircle2 size={28} className="shrink-0 text-ok" aria-hidden="true" />
        <div>
          <p className="text-sm font-semibold text-ink">Không phát hiện bất thường</p>
          <p className="meta mt-0.5">Isolation Forest không ghi nhận sự cố trong thời gian theo dõi.</p>
        </div>
      </div>
    );
  }

  return (
    <section className="panel overflow-hidden" aria-label="Danh sách sự cố bất thường">
      <div className="panel-head">
        <h3 className="panel-title flex items-center gap-2.5">
          Danh sách sự cố bất thường
          <span className="chip chip-crit num">{anomalies.length}</span>
        </h3>
        <p className="meta">Mới nhất · Isolation Forest</p>
      </div>

      <div className="max-h-[340px] overflow-auto">
        <table className="w-full min-w-[620px] border-collapse text-left text-sm">
          <thead className="sticky top-0 z-10 bg-sunken text-xs text-muted">
            <tr>
              <th scope="col" className="px-4 py-2 font-medium">Mức độ · Hệ thống</th>
              <th scope="col" className="px-3 py-2 font-medium">Thời điểm</th>
              <th scope="col" className="px-3 py-2 text-right font-medium">Δ kWh</th>
              <th scope="col" className="px-3 py-2 text-right font-medium">Điểm</th>
              <th scope="col" className="px-3 py-2 text-right font-medium">Nhiệt độ</th>
              <th scope="col" className="px-3 py-2 text-right font-medium">Lãng phí</th>
              <th scope="col" className="px-4 py-2"><span className="sr-only">Hành động</span></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {anomalies.map((anom) => {
              const severity = String(anom.severity || 'Low');
              const cfg = SEVERITY_CONFIG[severity.charAt(0).toUpperCase() + severity.slice(1).toLowerCase()] || SEVERITY_CONFIG.Low;
              const ts  = anom.timestamp?.slice(0, 16)?.replace('T', ' ') || '—';
              return (
                <tr key={anom.id} className="align-top hover:bg-sunken/70">
                  <td className="relative px-4 py-3">
                    <span className={`absolute inset-y-2 left-0 w-0.5 ${cfg.row}`} aria-hidden="true" />
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={`chip uppercase ${cfg.chip}`}>{anom.severity}</span>
                      <span className="font-medium text-ink">{anom.subsystem}</span>
                    </div>
                    {anom.description && (
                      <p className="mt-1 max-w-sm truncate text-xs text-muted">{anom.description}</p>
                    )}
                  </td>
                  <td className="num whitespace-nowrap px-3 py-3 text-xs text-ink-2">{ts}</td>
                  <td className="num whitespace-nowrap px-3 py-3 text-right font-semibold text-crit">
                    {anom.delta_kwh == null ? '—' : `+${anom.delta_kwh} kWh`}
                  </td>
                  <td className="num px-3 py-3 text-right text-ink-2">{anom.anomaly_score?.toFixed(2)}</td>
                  <td className="num whitespace-nowrap px-3 py-3 text-right text-ink-2">{anom.outdoor_temp_c ?? '—'}°C</td>
                  <td className="whitespace-nowrap px-3 py-3 text-right">
                    <p className="num font-semibold text-ink">{anom.estimated_waste_vnd?.toLocaleString('vi-VN') ?? '—'} đ</p>
                    <p className="num text-xs text-muted">${anom.estimated_waste_usd ?? '—'}</p>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      id={`ask-copilot-${anom.id}`}
                      onClick={() => onAskCopilot?.(anom)}
                      className="btn btn-quiet btn-sm"
                      title="Hỏi Copilot về sự cố này"
                    >
                      <MessageSquare size={13} aria-hidden="true" />
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

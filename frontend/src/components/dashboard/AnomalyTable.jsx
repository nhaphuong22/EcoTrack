import { AlertTriangle, MessageSquare, Clock } from 'lucide-react';

const SEVERITY_CONFIG = {
  Critical: { badge: 'bg-rose-500/20 text-rose-300 border-rose-500/30', dot: 'bg-rose-500' },
  Medium:   { badge: 'bg-amber-500/20 text-amber-300 border-amber-500/30', dot: 'bg-amber-500' },
  Low:      { badge: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/30', dot: 'bg-yellow-400' },
  Normal:   { badge: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30', dot: 'bg-emerald-500' },
};

export default function AnomalyTable({ anomalies, loading, onAskCopilot }) {
  if (loading) {
    return (
      <div className="space-y-2">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="h-16 animate-pulse rounded-xl bg-slate-800/60" />
        ))}
      </div>
    );
  }

  if (!anomalies?.length) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-emerald-500/20 bg-emerald-500/5 py-10">
        <div className="rounded-full bg-emerald-500/10 p-4">
          <AlertTriangle size={28} className="text-emerald-400" />
        </div>
        <p className="text-sm font-medium text-emerald-400">Không phát hiện bất thường</p>
        <p className="text-xs text-slate-500">Isolation Forest không ghi nhận sự cố trong thời gian theo dõi.</p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-2xl border border-slate-700 bg-slate-800/60 backdrop-blur-sm">
      <div className="flex items-center justify-between border-b border-slate-700 px-5 py-3.5">
        <h3 className="font-semibold text-white">
          Danh sách sự cố bất thường
          <span className="ml-2 rounded-full bg-rose-500/20 px-2 py-0.5 text-xs font-bold text-rose-400">
            {anomalies.length}
          </span>
        </h3>
        <p className="text-xs text-slate-400">Mới nhất · Isolation Forest</p>
      </div>

      <div className="divide-y divide-slate-700/50 max-h-72 overflow-y-auto">
        {anomalies.map((anom) => {
          const cfg = SEVERITY_CONFIG[anom.severity] || SEVERITY_CONFIG.Low;
          const ts  = anom.timestamp?.slice(0, 16)?.replace('T', ' ') || '—';
          return (
            <div
              key={anom.id}
              className="group flex items-center gap-4 px-5 py-3.5 transition hover:bg-slate-700/30"
            >
              {/* Severity dot */}
              <span className={`h-2.5 w-2.5 flex-shrink-0 rounded-full ${cfg.dot} animate-pulse`} />

              {/* Info */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className={`rounded border px-1.5 py-0.5 text-[10px] font-bold uppercase ${cfg.badge}`}>
                    {anom.severity}
                  </span>
                  <span className="text-xs font-medium text-slate-200 truncate">{anom.subsystem}</span>
                </div>
                <p className="mt-0.5 flex items-center gap-1.5 text-[11px] text-slate-400">
                  <Clock size={10} />
                  {ts} · Δ <strong className="text-rose-300">+{anom.delta_kwh} kWh</strong>
                  · Score: {anom.anomaly_score?.toFixed(2)}
                  · 🌡️ {anom.outdoor_temp_c}°C
                </p>
                {anom.description && (
                  <p className="mt-0.5 text-[11px] text-slate-500 truncate">{anom.description}</p>
                )}
              </div>

              {/* Cost estimate */}
              <div className="hidden text-right sm:block flex-shrink-0">
                <p className="text-xs font-semibold text-rose-400">
                  {anom.estimated_waste_vnd?.toLocaleString('vi-VN')} đ
                </p>
                <p className="text-[10px] text-slate-500">${anom.estimated_waste_usd}</p>
              </div>

              {/* Ask Copilot */}
              <button
                id={`ask-copilot-${anom.id}`}
                onClick={() => onAskCopilot?.(anom)}
                className="flex flex-shrink-0 items-center gap-1.5 rounded-lg border border-sky-500/30 bg-sky-500/10 px-2.5 py-1.5 text-[11px] font-medium text-sky-400 opacity-0 transition hover:bg-sky-500/20 group-hover:opacity-100"
                title="Chẩn đoán sự cố này bằng Copilot"
                aria-label={`Chẩn đoán bằng Copilot cho sự cố ${anom.id}`}
              >
                <MessageSquare size={12} />
                Chẩn đoán bằng Copilot
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}

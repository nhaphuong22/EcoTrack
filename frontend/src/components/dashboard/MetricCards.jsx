import { Zap, TrendingUp, AlertTriangle, Banknote } from 'lucide-react';

// One instrument strip, not four floating cards. State tint appears only where a value carries a state.
function Reading({ icon: Icon, label, value, unit, subLabel, tone = 'neutral' }) {
  const toneText = { neutral: 'text-ink', warn: 'text-warn', crit: 'text-crit', ok: 'text-ok' }[tone];
  const toneBar = { neutral: 'bg-line-strong', warn: 'bg-warn-fill', crit: 'bg-crit', ok: 'bg-ok' }[tone];
  return (
    <div className="relative bg-panel px-5 py-4">
      <span className={`absolute inset-x-5 top-0 h-0.5 ${toneBar}`} aria-hidden="true" />
      <p className="flex items-center gap-2 text-[13px] font-medium text-muted">
        <Icon size={15} aria-hidden="true" />
        {label}
      </p>
      <p className={`num mt-2 flex items-baseline gap-1.5 text-[28px] font-semibold leading-none ${toneText}`}>
        {value}
        {unit && <span className="text-sm font-medium text-muted">{unit}</span>}
      </p>
      {subLabel && <p className="mt-2 text-xs text-muted">{subLabel}</p>}
    </div>
  );
}

export default function MetricCards({ metrics }) {
  if (!metrics) {
    return (
      <div className="panel grid animate-pulse grid-cols-2 gap-px overflow-hidden bg-line lg:grid-cols-4" aria-busy="true">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="h-[108px] bg-panel p-5">
            <div className="h-3 w-24 rounded bg-sunken" />
            <div className="mt-4 h-7 w-32 rounded bg-sunken" />
          </div>
        ))}
      </div>
    );
  }

  const {
    total_consumption_kwh,
    peak_demand_kw,
    total_anomalies_detected,
    estimated_waste_cost_vnd,
  } = metrics;

  const readings = [
    {
      icon: Zap,
      label: 'Tổng điện tiêu thụ (30 ngày)',
      value: (total_consumption_kwh / 1000).toFixed(1),
      unit: 'MWh',
      subLabel: `${total_consumption_kwh.toLocaleString('vi-VN')} kWh`,
    },
    {
      icon: TrendingUp,
      label: 'Công suất đỉnh (Peak)',
      value: peak_demand_kw.toFixed(0),
      unit: 'kW',
      subLabel: 'Ghi nhận gần nhất',
    },
    {
      icon: AlertTriangle,
      label: 'Sự cố bất thường',
      value: total_anomalies_detected,
      subLabel: 'Isolation Forest phát hiện',
      tone: total_anomalies_detected > 0 ? 'warn' : 'ok',
    },
    {
      icon: Banknote,
      label: 'Ước tính lãng phí',
      value: (estimated_waste_cost_vnd / 1000).toFixed(0),
      unit: 'K VNĐ',
      subLabel: `≈ $${(estimated_waste_cost_vnd / 25000).toFixed(0)} USD`,
      tone: estimated_waste_cost_vnd > 0 ? 'crit' : 'neutral',
    },
  ];

  return (
    <div className="panel grid grid-cols-2 gap-px overflow-hidden bg-line lg:grid-cols-4">
      {readings.map((r) => (
        <Reading key={r.label} {...r} />
      ))}
    </div>
  );
}

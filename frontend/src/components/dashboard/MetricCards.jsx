import { Zap, TrendingUp, AlertTriangle, DollarSign } from 'lucide-react';

function StatCard({ icon: Icon, label, value, subLabel, color, glowColor }) {
  return (
    <div
      className={`relative overflow-hidden rounded-2xl border ${color} bg-slate-800/60 p-5 backdrop-blur-sm transition hover:scale-[1.01]`}
      style={{ boxShadow: `0 0 24px -8px ${glowColor}` }}
    >
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-widest text-slate-400">{label}</p>
          <p className="mt-1 text-2xl font-bold text-white">{value}</p>
          {subLabel && <p className="mt-0.5 text-xs text-slate-400">{subLabel}</p>}
        </div>
        <div className={`rounded-xl p-2 ${color.replace('border-', 'bg-').replace('/40', '/15')}`}>
          <Icon size={22} className="text-current opacity-80" />
        </div>
      </div>
    </div>
  );
}

export default function MetricCards({ metrics }) {
  if (!metrics) {
    return (
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="h-28 animate-pulse rounded-2xl bg-slate-800/60" />
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

  const cards = [
    {
      icon: Zap,
      label: 'Tổng điện tiêu thụ (30 ngày)',
      value: `${(total_consumption_kwh / 1000).toFixed(1)} MWh`,
      subLabel: `${total_consumption_kwh.toLocaleString('vi-VN')} kWh`,
      color: 'border-emerald-500/40 text-emerald-400',
      glowColor: 'rgba(52,211,153,0.18)',
    },
    {
      icon: TrendingUp,
      label: 'Công suất đỉnh (Peak)',
      value: `${peak_demand_kw.toFixed(0)} kW`,
      subLabel: 'Ghi nhận gần nhất',
      color: 'border-sky-500/40 text-sky-400',
      glowColor: 'rgba(56,189,248,0.18)',
    },
    {
      icon: AlertTriangle,
      label: 'Sự cố bất thường',
      value: total_anomalies_detected,
      subLabel: 'Isolation Forest phát hiện',
      color:
        total_anomalies_detected > 0
          ? 'border-amber-500/40 text-amber-400'
          : 'border-emerald-500/40 text-emerald-400',
      glowColor:
        total_anomalies_detected > 0
          ? 'rgba(251,191,36,0.18)'
          : 'rgba(52,211,153,0.18)',
    },
    {
      icon: DollarSign,
      label: 'Ước tính lãng phí',
      value: `${(estimated_waste_cost_vnd / 1000).toFixed(0)}K VNĐ`,
      subLabel: `≈ $${(estimated_waste_cost_vnd / 25000).toFixed(0)} USD`,
      color: 'border-rose-500/40 text-rose-400',
      glowColor: 'rgba(251,113,133,0.18)',
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      {cards.map(c => (
        <StatCard key={c.label} {...c} />
      ))}
    </div>
  );
}

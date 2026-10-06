import {
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
} from 'recharts';
import { format, parseISO } from 'date-fns';

const AnomalyDot = ({ cx, cy, payload }) => {
  if (!payload?.is_anomaly || !Number.isFinite(cx) || !Number.isFinite(cy)) return null;

  return (
    <g className="anomaly-marker" aria-label={`Sự cố điện lúc ${payload.label}`}>
      <circle className="anomaly-marker__halo" cx={cx} cy={cy} r={9} fill="#fb7185" />
      <circle cx={cx} cy={cy} r={5} fill="#ef4444" stroke="#fecdd3" strokeWidth={2} />
    </g>
  );
};

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  const actual     = payload.find(p => p.dataKey === 'meter_reading_kwh');
  const predicted  = payload.find(p => p.dataKey === 'predicted_kwh');
  const isAnomaly  = payload[0]?.payload?.is_anomaly;

  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900/95 p-3 shadow-xl backdrop-blur-sm text-xs">
      <p className="mb-2 font-semibold text-slate-300">{label}</p>
      {actual && (
        <p className={`flex gap-2 ${isAnomaly ? 'text-rose-400' : 'text-emerald-400'}`}>
          <span>⚡ Thực tế:</span>
          <span className="font-bold">{actual.value?.toFixed(1)} kWh</span>
          {isAnomaly && <span className="rounded bg-rose-500/20 px-1 text-rose-300">⚠ Anomaly</span>}
        </p>
      )}
      {predicted && (
        <p className="flex gap-2 text-sky-400">
          <span>📊 Dự báo:</span>
          <span className="font-bold">{predicted.value?.toFixed(1)} kWh</span>
        </p>
      )}
      {actual && predicted && (
        <p className="mt-1 border-t border-slate-700 pt-1 text-slate-400">
          Δ {(actual.value - predicted.value).toFixed(1)} kWh
        </p>
      )}
    </div>
  );
};

export default function ForecastChart({ timeSeries, loading }) {
  if (loading) {
    return (
      <div className="flex h-72 items-center justify-center rounded-2xl border border-slate-700 bg-slate-800/60">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-emerald-500/30 border-t-emerald-500" />
      </div>
    );
  }

  // Downsample to last 72 data points for readability
  const chartData = timeSeries.slice(-72).map(d => ({
    ...d,
    // A two-value Area is a true band between the API-provided bounds.
    confidence_interval_95:
      Number.isFinite(d.lower_bound_95) && Number.isFinite(d.upper_bound_95)
        ? [d.lower_bound_95, d.upper_bound_95]
        : null,
    label: (() => {
      try { return format(parseISO(d.timestamp), 'MM/dd HH:mm'); }
      catch { return d.timestamp?.slice(5, 16) || ''; }
    })(),
  }));

  return (
    <div className="rounded-2xl border border-slate-700 bg-slate-800/60 p-5 backdrop-blur-sm">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h3 className="font-semibold text-white">Phụ tải điện: Thực tế vs. Dự báo (XGBoost)</h3>
          <p className="text-xs text-slate-400">72 giờ gần nhất · Dải tin cậy 95%</p>
        </div>
        <div className="flex items-center gap-4 text-xs text-slate-400">
          <span className="flex items-center gap-1"><span className="inline-block h-0.5 w-4 bg-emerald-400" />Thực tế</span>
          <span className="flex items-center gap-1"><span className="inline-block h-0.5 w-4 border-t border-dashed border-sky-400" />Dự báo</span>
          <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full bg-rose-400" />Anomaly</span>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={280}>
        <ComposedChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id="confGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#38bdf8" stopOpacity={0.18} />
              <stop offset="100%" stopColor="#38bdf8" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
          <XAxis
            dataKey="label"
            tick={{ fill: '#64748b', fontSize: 10 }}
            tickLine={false}
            interval={11}
          />
          <YAxis
            tick={{ fill: '#64748b', fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            unit=" kWh"
            width={56}
          />
          <Tooltip content={<CustomTooltip />} />

          {/* 95% confidence band */}
          <Area
            dataKey="confidence_interval_95"
            type="monotone"
            stroke="none"
            fill="url(#confGrad)"
            legendType="none"
            name="Khoảng tin cậy 95%"
            connectNulls
            isAnimationActive={false}
          />

          {/* Predicted baseline */}
          <Line
            dataKey="predicted_kwh"
            stroke="#38bdf8"
            strokeWidth={1.5}
            strokeDasharray="5 3"
            dot={false}
            name="Dự báo XGBoost"
            activeDot={{ r: 4 }}
          />

          {/* Actual metered load */}
          <Line
            dataKey="meter_reading_kwh"
            stroke="#34d399"
            strokeWidth={2}
            dot={<AnomalyDot />}
            name="Thực tế"
            activeDot={{ r: 5, fill: '#34d399' }}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

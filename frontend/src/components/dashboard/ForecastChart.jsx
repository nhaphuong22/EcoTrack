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
    <div className="rounded-md border border-line-strong bg-panel p-3 text-xs shadow-[0_8px_24px_-8px_rgba(14,30,29,0.25)]">
      <p className="num mb-2 font-semibold text-ink">{label}</p>
      {actual && (
        <p className="flex items-center justify-between gap-6 text-ink">
          <span className="text-muted">Thực tế</span>
          <span className="num font-semibold">{actual.value?.toFixed(1)} kWh</span>
          {isAnomaly && <span className="chip chip-crit">Anomaly</span>}
        </p>
      )}
      {predicted && (
        <p className="mt-1 flex items-center justify-between gap-6 text-signal">
          <span className="text-muted">Dự báo</span>
          <span className="num font-semibold">{predicted.value?.toFixed(1)} kWh</span>
        </p>
      )}
      {actual && predicted && (
        <p className="num mt-2 border-t border-line pt-2 text-muted">
          Δ {(actual.value - predicted.value).toFixed(1)} kWh
        </p>
      )}
    </div>
  );
};

export default function ForecastChart({ timeSeries, forecast = [], loading }) {
  if (loading) {
    return (
      <div className="panel flex h-[360px] items-center justify-center" aria-busy="true">
        <div className="h-7 w-7 animate-spin rounded-full border-[3px] border-line border-t-shell" />
      </div>
    );
  }

  // Show the observed window followed by future-only predictions.
  const chartData = [...timeSeries.slice(-72), ...forecast.map((point) => ({
    ...point, meter_reading_kwh: null, is_anomaly: false,
  }))].map(d => ({
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
    <section className="panel" aria-label="Biểu đồ phụ tải">
      <div className="panel-head">
        <div>
          <h3 className="panel-title">Phụ tải điện: Thực tế vs. Dự báo (XGBoost)</h3>
          <p className="meta mt-0.5">72 giờ gần nhất · Dự báo 24 giờ tới · Dải tin cậy 95%</p>
        </div>
        <div className="flex items-center gap-5 text-xs text-ink-2">
          <span className="flex items-center gap-2"><span className="inline-block h-0.5 w-5 bg-shell" />Thực tế</span>
          <span className="flex items-center gap-2"><span className="inline-block w-5 border-t-2 border-dashed border-signal" />Dự báo</span>
          <span className="flex items-center gap-2"><span className="inline-block h-2.5 w-2.5 rounded-full bg-crit" />Anomaly</span>
        </div>
      </div>

      <div className="px-2 pb-3 pt-4 sm:px-4">
      <ResponsiveContainer width="100%" height={300}>
        <ComposedChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id="confGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#1f55cc" stopOpacity={0.16} />
              <stop offset="100%" stopColor="#1f55cc" stopOpacity={0.05} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#d2dbd8" strokeDasharray="2 4" vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fill: '#54655f', fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: '#a9b8b3' }}
            interval={11}
          />
          <YAxis
            tick={{ fill: '#54655f', fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            unit=" kWh"
            width={56}
          />
          <Tooltip content={<CustomTooltip />} />
          {forecast.length > 0 && timeSeries.length > 0 && (
            <ReferenceLine x={chartData[Math.min(timeSeries.length, 72) - 1]?.label}
              stroke="#0e1e1d" strokeDasharray="3 3" label={{ value: 'Hiện tại', fill: '#0e1e1d', fontSize: 11, position: 'insideTopLeft' }} />
          )}

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
            stroke="#1f55cc"
            strokeWidth={1.75}
            strokeDasharray="5 3"
            dot={false}
            name="Dự báo XGBoost"
            activeDot={{ r: 4, fill: '#1f55cc' }}
          />

          {/* Actual metered load */}
          <Line
            dataKey="meter_reading_kwh"
            stroke="#0c3a3e"
            strokeWidth={2.25}
            dot={<AnomalyDot />}
            name="Thực tế"
            activeDot={{ r: 5, fill: '#0c3a3e' }}
          />
        </ComposedChart>
      </ResponsiveContainer>
      </div>
    </section>
  );
}

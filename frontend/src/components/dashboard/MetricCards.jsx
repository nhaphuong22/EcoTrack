import { Zap, Gauge, AlertTriangle, TrendingDown, ArrowRight } from 'lucide-react';
import { format, parseISO } from 'date-fns';

function formatPeakTime(timeSeries = []) {
  if (!timeSeries.length) return 'Mức cao nhất trong kỳ';
  let maxPoint = timeSeries[0];
  for (const point of timeSeries) {
    if ((point?.meter_reading_kwh ?? -Infinity) > (maxPoint?.meter_reading_kwh ?? -Infinity)) {
      maxPoint = point;
    }
  }
  if (!maxPoint?.timestamp) return 'Mức cao nhất trong kỳ';
  try {
    return `Đạt lúc ${format(parseISO(maxPoint.timestamp), 'HH:mm, dd/MM')}`;
  } catch {
    return 'Mức cao nhất trong kỳ';
  }
}

function formatWasteValue(vnd) {
  if (vnd >= 1_000_000) {
    return { value: (vnd / 1_000_000).toFixed(2), unit: 'M VNĐ' };
  }
  if (vnd >= 1_000) {
    return { value: (vnd / 1_000).toFixed(0), unit: 'K VNĐ' };
  }
  if (vnd > 0) {
    return { value: (vnd / 1_000).toFixed(2), unit: 'K VNĐ' };
  }
  return { value: '0', unit: 'VNĐ' };
}

function MetricCard({ icon: Icon, iconTone, label, value, unit, valueTone = 'text-ink', footer }) {
  return (
    <article className="panel flex flex-col justify-between p-5">
      <div className="flex items-start justify-between gap-3">
        <p className="text-[13px] font-medium text-muted">{label}</p>
        <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${iconTone}`}>
          <Icon size={17} aria-hidden="true" />
        </span>
      </div>

      <p className={`num mt-3 flex items-baseline gap-1.5 text-[30px] font-bold leading-none ${valueTone}`}>
        <span>{value}</span>
        {unit && <span className="text-sm font-medium text-muted">{unit}</span>}
      </p>

      <div className="mt-3.5 text-xs text-muted">{footer}</div>
    </article>
  );
}

export default function MetricCards({ metrics, anomalies = [], timeSeries = [], onViewAnomalies }) {
  if (!metrics) {
    return (
      <div className="grid animate-pulse grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-busy="true">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="panel h-[138px] p-5">
            <div className="flex items-center justify-between">
              <div className="h-3.5 w-28 rounded bg-sunken" />
              <div className="h-9 w-9 rounded-xl bg-sunken" />
            </div>
            <div className="mt-5 h-7 w-24 rounded bg-sunken" />
            <div className="mt-4 h-3 w-36 rounded bg-sunken" />
          </div>
        ))}
      </div>
    );
  }

  const {
    total_consumption_kwh = 0,
    peak_demand_kw = 0,
    total_anomalies_detected = 0,
    estimated_waste_cost_vnd = 0,
    estimated_waste_cost_usd,
  } = metrics;

  const usdValue = estimated_waste_cost_usd ?? estimated_waste_cost_vnd / 25000;
  const formattedUsd = usdValue > 0 && usdValue < 10 ? usdValue.toFixed(2) : usdValue.toFixed(0);
  const waste = formatWasteValue(estimated_waste_cost_vnd);
  const openCount = anomalies.filter(
    (item) => String(item?.status || 'OPEN').toUpperCase() === 'OPEN',
  ).length;
  const peakFooter = formatPeakTime(timeSeries);

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <MetricCard
        icon={Zap}
        iconTone="bg-ok-bg text-ok"
        label="Điện năng (30 ngày)"
        value={(total_consumption_kwh / 1000).toFixed(1)}
        unit="MWh"
        footer={
          <span>
            Tổng tiêu thụ <span className="num font-medium text-ink-2">{total_consumption_kwh.toLocaleString('vi-VN')} kWh</span>
          </span>
        }
      />

      <MetricCard
        icon={Gauge}
        iconTone="bg-sunken text-shell"
        label="Công suất đỉnh"
        value={peak_demand_kw.toFixed(0)}
        unit="kW"
        footer={<span>{peakFooter}</span>}
      />

      <MetricCard
        icon={AlertTriangle}
        iconTone={total_anomalies_detected > 0 ? 'bg-warn-bg text-warn' : 'bg-ok-bg text-ok'}
        label="Sự cố bất thường"
        value={total_anomalies_detected}
        unit="cảnh báo"
        valueTone={total_anomalies_detected > 0 ? 'text-warn' : 'text-ok'}
        footer={
          openCount > 0 ? (
            <button
              type="button"
              onClick={onViewAnomalies}
              className="inline-flex items-center gap-1.5 rounded-full bg-warn-bg px-2.5 py-0.5 font-semibold text-warn transition-opacity hover:opacity-85"
            >
              <span>{openCount} sự cố chưa xử lý</span>
              <ArrowRight size={12} aria-hidden="true" />
            </button>
          ) : total_anomalies_detected > 0 ? (
            <span className="font-medium text-ok">Tất cả đã được xử lý</span>
          ) : (
            <span className="font-medium text-ok">Hệ thống vận hành ổn định</span>
          )
        }
      />

      <MetricCard
        icon={TrendingDown}
        iconTone={estimated_waste_cost_vnd > 0 ? 'bg-crit-bg text-crit' : 'bg-sunken text-muted'}
        label="Lãng phí ước tính"
        value={waste.value}
        unit={waste.unit}
        valueTone={estimated_waste_cost_vnd > 0 ? 'text-crit' : 'text-ink'}
        footer={
          <span>
            <span className="num font-medium text-ink-2">≈ ${formattedUsd} USD</span> · Biểu giá điện
          </span>
        }
      />
    </div>
  );
}

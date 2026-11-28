export default function PortalSparkline({ points = [], formatValue }) {
  const series = points.slice(-24);
  if (series.length < 2) return null;

  const values = series.map((p) => Number(p?.meter_reading_kwh ?? 0));
  const avg = values.reduce((sum, v) => sum + v, 0) / values.length;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;

  const width = 360;
  const height = 72;
  const padX = 6;
  const padY = 8;

  const coords = values.map((val, idx) => {
    const x = padX + (idx / (values.length - 1)) * (width - padX * 2);
    const y = height - padY - ((val - min) / span) * (height - padY * 2);
    return [x, y];
  });

  const linePath = coords
    .map(([x, y], idx) => `${idx === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`)
    .join(' ');
  const areaPath = `${linePath} L${coords[coords.length - 1][0].toFixed(1)},${height} L${coords[0][0].toFixed(1)},${height} Z`;
  const [lastX, lastY] = coords[coords.length - 1];

  return (
    <div className="rounded-xl border border-line bg-sunken/50 p-3.5">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-xs">
        <span className="font-medium text-muted">Xu hướng {series.length} thời điểm gần nhất</span>
        <span className="num font-semibold text-ok">
          Trung bình: {formatValue ? formatValue(avg) : avg.toFixed(2)} kWh
        </span>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} className="h-16 w-full overflow-visible" aria-hidden="true">
        <defs>
          <linearGradient id="portalSparkGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#147246" stopOpacity="0.22" />
            <stop offset="100%" stopColor="#147246" stopOpacity="0.02" />
          </linearGradient>
        </defs>
        <path d={areaPath} fill="url(#portalSparkGrad)" />
        <path d={linePath} fill="none" stroke="#147246" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx={lastX} cy={lastY} r="3.5" fill="#147246" stroke="#ffffff" strokeWidth="1.5" />
      </svg>
    </div>
  );
}

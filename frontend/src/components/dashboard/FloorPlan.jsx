import { useState, useEffect } from 'react';
import { Thermometer, Zap, Radio, Info } from 'lucide-react';
import { fetchZones } from '../../services/api';
import { useLiveReadings } from '../../hooks/useLiveReadings';
import ZoneDetailModal from './ZoneDetailModal';

// Room states: fill and stroke are drawn in the SVG, `textColor` is for any HTML consumer.
const NO_READING = { fill: '#edf1ef', stroke: '#a9b8b3', statusText: 'Chưa có đo', textColor: 'text-muted' };

// Helper to determine color and text status for temperature
function getTempColorAndStatus(temp) {
  if (!Number.isFinite(temp)) return NO_READING;
  if (temp < 22) return { fill: '#dce7fb', stroke: '#1f55cc', statusText: 'Mát lạnh', textColor: 'text-signal' };
  if (temp <= 25) return { fill: '#d9efe2', stroke: '#17784a', statusText: 'Tối ưu', textColor: 'text-ok' };
  if (temp <= 28) return { fill: '#fbecc9', stroke: '#c07a00', statusText: 'Hơi ấm', textColor: 'text-warn' };
  return { fill: '#fbdad6', stroke: '#bd2630', statusText: 'Nhiệt cao', textColor: 'text-crit' };
}

// Helper to determine color and text status for energy waste/consumption
function getWasteColorAndStatus(kwh) {
  if (!Number.isFinite(kwh)) return NO_READING;
  if (kwh < 40) return { fill: '#d9efe2', stroke: '#17784a', statusText: 'Tiết kiệm', textColor: 'text-ok' };
  if (kwh <= 80) return { fill: '#fbecc9', stroke: '#c07a00', statusText: 'Trung bình', textColor: 'text-warn' };
  return { fill: '#fbdad6', stroke: '#bd2630', statusText: 'Lãng phí cao', textColor: 'text-crit' };
}

// Coordinates map for the 10 rooms (5 North Wing rooms, 5 South Wing rooms)
// SVG Canvas width = 1000, height = 540
const ROOM_LAYOUTS = [
  // North Wing (Rooms 101 - 105)
  { id: 'z1', x: 40, y: 50, w: 170, h: 180, label: 'Phòng 101' },
  { id: 'z2', x: 230, y: 50, w: 170, h: 180, label: 'Phòng 102' },
  { id: 'z3', x: 420, y: 50, w: 170, h: 180, label: 'Phòng 103' },
  { id: 'z4', x: 610, y: 50, w: 170, h: 180, label: 'Phòng 104' },
  { id: 'z5', x: 800, y: 50, w: 170, h: 180, label: 'Phòng 105' },

  // South Wing (Rooms 106 - 110)
  { id: 'z6', x: 40, y: 310, w: 170, h: 180, label: 'Phòng 106' },
  { id: 'z7', x: 230, y: 310, w: 170, h: 180, label: 'Phòng 107' },
  { id: 'z8', x: 420, y: 310, w: 170, h: 180, label: 'Phòng 108' },
  { id: 'z9', x: 610, y: 310, w: 170, h: 180, label: 'Phòng 109' },
  { id: 'z10', x: 800, y: 310, w: 170, h: 180, label: 'Phòng 110' },
];

export default function FloorPlan({ buildingId = 'office_tower_01', onAskCopilot }) {
  const [initialZones, setInitialZones] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [metricMode, setMetricMode] = useState('temp'); // 'temp' | 'waste'
  const [selectedZone, setSelectedZone] = useState(null);

  // Load initial zones list
  useEffect(() => {
    let isMounted = true;
    setLoading(true);

    fetchZones(buildingId)
      .then((data) => {
        if (isMounted) {
          setInitialZones(data.zones || []);
          setError(null);
        }
      })
      .catch((err) => {
        if (isMounted) {
          console.error('[FloorPlan] Failed to fetch initial zones:', err);
          setError(err.message || 'Không thể tải danh sách khu vực');
        }
      })
      .finally(() => {
        if (isMounted) setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [buildingId]);

  // Hook live readings from SSE stream
  const { zones, isConnected, retryAttempt } = useLiveReadings(buildingId, initialZones);

  // Map zone data by ID for instant O(1) lookup
  const zoneDataMap = new Map((zones || []).map((z) => [z.id, z]));

  const segBtn = (active) =>
    `flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-semibold transition-colors ${
      active ? 'bg-shell text-white' : 'text-ink-2 hover:bg-sunken'
    }`;

  const legendTemp = [
    ['#1f55cc', '#dce7fb', '<22°C (Mát)'],
    ['#17784a', '#d9efe2', '22-25°C (Chuẩn)'],
    ['#c07a00', '#fbecc9', '25-28°C (Ấm)'],
    ['#bd2630', '#fbdad6', '>28°C (Nóng)'],
  ];
  const legendWaste = [
    ['#17784a', '#d9efe2', '<40 kWh (Thấp)'],
    ['#c07a00', '#fbecc9', '40-80 kWh (Vừa)'],
    ['#bd2630', '#fbdad6', '>80 kWh (Cao)'],
  ];

  return (
    <section className="panel">
      {/* Control Bar: Header, Metric Toggle, Stream Status */}
      <div className="panel-head gap-y-3 py-3.5">
        <div>
          <div className="flex items-center gap-2.5">
            <h2 className="panel-title text-base">Sơ đồ Mặt bằng Thời gian thực</h2>
            <span className="chip chip-mute">Tầng 1</span>
          </div>
          <p className="meta mt-0.5">
            Mô phỏng 10 khu vực làm việc • Cập nhật tự động qua luồng Server-Sent Events (SSE)
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-1 rounded-md border border-line-strong bg-panel p-1" role="group" aria-label="Chỉ số hiển thị">
            <button
              id="mode-toggle-temp"
              onClick={() => setMetricMode('temp')}
              aria-pressed={metricMode === 'temp'}
              className={segBtn(metricMode === 'temp')}
            >
              <Thermometer size={14} aria-hidden="true" />
              <span>Nhiệt độ</span>
            </button>
            <button
              id="mode-toggle-waste"
              onClick={() => setMetricMode('waste')}
              aria-pressed={metricMode === 'waste'}
              className={segBtn(metricMode === 'waste')}
            >
              <Zap size={14} aria-hidden="true" />
              <span>Lãng phí</span>
            </button>
          </div>

          <div
            id="stream-connection-badge"
            className={`chip px-2.5 py-1.5 text-xs ${isConnected ? 'chip-ok' : 'chip-crit'}`}
            title={isConnected ? 'Đang kết nối live stream' : 'Mất kết nối với SSE server'}
          >
            <Radio size={13} className={isConnected ? 'animate-pulse' : ''} aria-hidden="true" />
            <span>
              {isConnected ? 'Trực tuyến' : `Mất kết nối${retryAttempt > 0 ? ` (thử lại #${retryAttempt})` : ''}`}
            </span>
          </div>
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div role="alert" className="m-4 flex items-center gap-2 rounded-md border border-crit/30 bg-crit-bg p-3 text-xs text-crit">
          <Info size={14} aria-hidden="true" />
          <span>Lỗi tải sơ đồ: {error}</span>
        </div>
      )}

      {/* SVG Floor Plan Canvas */}
      <div className="relative m-4 overflow-hidden rounded border border-line-strong bg-white p-3">
        {loading && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-white/85 text-sm text-ink-2" aria-busy="true">
            <span className="mr-2 inline-block h-4 w-4 animate-spin rounded-full border-2 border-line border-t-shell" aria-hidden="true" />
            Đang tải sơ đồ mặt bằng...
          </div>
        )}

        <svg
          viewBox="0 0 1010 540"
          className="h-auto max-h-[580px] w-full select-none"
          role="img"
          aria-label="Sơ đồ mặt bằng toà nhà Tầng 1"
        >
          {/* Outer wall: heavy architectural line */}
          <rect x="15" y="15" width="980" height="510" fill="none" stroke="#0e1e1d" strokeWidth="5" />

          {/* Central corridor, hatched like a drawing's circulation space */}
          <defs>
            <pattern id="corridor-hatch" width="10" height="10" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <line x1="0" y1="0" x2="0" y2="10" stroke="#c9d3cf" strokeWidth="1.5" />
            </pattern>
          </defs>
          <rect x="30" y="238" width="950" height="64" fill="url(#corridor-hatch)" stroke="#a9b8b3" strokeWidth="1" />
          <rect x="360" y="256" width="290" height="28" fill="#ffffff" />
          <text x="505" y="275" textAnchor="middle" fill="#3b4d4a" fontSize="12" letterSpacing="2.5" fontWeight="600">
            HÀNH LANG TRUNG TÂM • TẦNG 1
          </text>

          {/* 10 Interactive Zones */}
          {ROOM_LAYOUTS.map((layout) => {
            const zoneData = zoneDataMap.get(layout.id) || {
              id: layout.id,
              name: layout.label,
              floor: 1,
              latest_reading: {},
            };
            const reading = zoneData.latest_reading || {};

            const tempVal = reading.outdoor_temperature_c;
            const kwhVal = reading.meter_reading_kwh;

            const style =
              metricMode === 'temp'
                ? getTempColorAndStatus(tempVal)
                : getWasteColorAndStatus(kwhVal);

            const displayValue =
              metricMode === 'temp'
                ? Number.isFinite(tempVal)
                  ? `${tempVal.toFixed(1)}°C`
                  : '--°C'
                : Number.isFinite(kwhVal)
                ? `${kwhVal > 0 && kwhVal < 1 ? kwhVal.toFixed(4) : kwhVal.toFixed(1)} kWh`
                : '-- kWh';

            const northRow = layout.y < 200;

            return (
              <g
                key={layout.id}
                role="button"
                tabIndex={0}
                aria-label={`${zoneData.name || layout.label}: ${displayValue}, trạng thái: ${style.statusText}`}
                onClick={() => setSelectedZone(zoneData)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    setSelectedZone(zoneData);
                  }
                }}
                className="group cursor-pointer focus:outline-none"
              >
                {/* Room: tinted by state, walled in ink */}
                <rect
                  x={layout.x}
                  y={layout.y}
                  width={layout.w}
                  height={layout.h}
                  fill={style.fill}
                  stroke="#0e1e1d"
                  strokeWidth="2.5"
                  className="transition-colors duration-500"
                />
                {/* State edge on the corridor side of the room */}
                <rect
                  x={layout.x}
                  y={northRow ? layout.y + layout.h - 6 : layout.y}
                  width={layout.w}
                  height="6"
                  fill={style.stroke}
                />
                {/* Hover / focus ring */}
                <rect
                  x={layout.x - 5}
                  y={layout.y - 5}
                  width={layout.w + 10}
                  height={layout.h + 10}
                  fill="none"
                  stroke="#1f55cc"
                  strokeWidth="3"
                  className="opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus:opacity-100"
                />

                <text
                  x={layout.x + 14}
                  y={layout.y + 26}
                  fill="#0e1e1d"
                  fontSize="13"
                  fontWeight="700"
                  className="pointer-events-none"
                >
                  {zoneData.name || layout.label}
                </text>
                <text
                  x={layout.x + layout.w - 12}
                  y={layout.y + 26}
                  textAnchor="end"
                  fill="#3b4d4a"
                  fontSize="10.5"
                  fontFamily="'JetBrains Mono', monospace"
                  className="pointer-events-none"
                >
                  {layout.id}
                </text>

                <text
                  x={layout.x + layout.w / 2}
                  y={layout.y + 88}
                  textAnchor="middle"
                  fill="#0e1e1d"
                  fontSize="24"
                  fontWeight="600"
                  fontFamily="'JetBrains Mono', monospace"
                  letterSpacing="-0.5"
                  className="pointer-events-none"
                >
                  {displayValue}
                </text>

                {/* Status as a word: colour is never the only signal */}
                <text
                  x={layout.x + layout.w / 2}
                  y={layout.y + 118}
                  textAnchor="middle"
                  fill="#0e1e1d"
                  fontSize="12.5"
                  fontWeight="600"
                  className="pointer-events-none"
                >
                  {style.statusText}
                </text>

                <text
                  x={layout.x + layout.w / 2}
                  y={layout.y + 146}
                  textAnchor="middle"
                  fill="#1f55cc"
                  fontSize="11"
                  fontWeight="600"
                  className="pointer-events-none opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus:opacity-100"
                >
                  Xem chi tiết &amp; hỏi AI →
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      {/* Legend */}
      <div className="flex flex-col items-start justify-between gap-3 border-t border-line px-4 py-3 text-xs sm:flex-row sm:items-center">
        <div className="text-muted">
          <span className="font-semibold text-ink">Dải màu ({metricMode === 'temp' ? 'Nhiệt độ' : 'Lãng phí'}):</span>{' '}
          mỗi khu vực thể hiện song song bằng màu sắc và chữ.
        </div>

        <ul className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
          {(metricMode === 'temp' ? legendTemp : legendWaste).map(([stroke, fill, text]) => (
            <li key={text} className="flex items-center gap-1.5 text-ink-2">
              <span className="h-3 w-3 border-2" style={{ background: fill, borderColor: stroke }} aria-hidden="true" />
              {text}
            </li>
          ))}
        </ul>
      </div>

      <ZoneDetailModal
        zone={selectedZone}
        isOpen={Boolean(selectedZone)}
        onClose={() => setSelectedZone(null)}
        onAskCopilot={onAskCopilot}
      />
    </section>
  );
}

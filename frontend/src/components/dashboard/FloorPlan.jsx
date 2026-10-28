import { useState, useEffect } from 'react';
import { Thermometer, Zap, Radio, Info } from 'lucide-react';
import { fetchZones } from '../../services/api';
import { useLiveReadings } from '../../hooks/useLiveReadings';
import ZoneDetailModal from './ZoneDetailModal';

// Helper to determine color and text status for temperature
function getTempColorAndStatus(temp) {
  if (!Number.isFinite(temp)) {
    return {
      fill: 'rgba(51, 65, 85, 0.6)',
      stroke: '#475569',
      statusText: 'Chưa có đo',
      textColor: 'text-slate-400',
    };
  }
  if (temp < 22) {
    return {
      fill: 'rgba(2, 132, 199, 0.45)', // Sky blue
      stroke: '#0284c7',
      statusText: 'Mát lạnh',
      textColor: 'text-sky-400',
    };
  }
  if (temp <= 25) {
    return {
      fill: 'rgba(16, 185, 129, 0.45)', // Emerald
      stroke: '#10b981',
      statusText: 'Tối ưu',
      textColor: 'text-emerald-400',
    };
  }
  if (temp <= 28) {
    return {
      fill: 'rgba(245, 158, 11, 0.45)', // Amber
      stroke: '#f59e0b',
      statusText: 'Hơi ấm',
      textColor: 'text-amber-400',
    };
  }
  return {
    fill: 'rgba(239, 68, 68, 0.55)', // Rose/Red
    stroke: '#ef4444',
    statusText: 'Nhiệt cao',
    textColor: 'text-rose-400',
  };
}

// Helper to determine color and text status for energy waste/consumption
function getWasteColorAndStatus(kwh) {
  if (!Number.isFinite(kwh)) {
    return {
      fill: 'rgba(51, 65, 85, 0.6)',
      stroke: '#475569',
      statusText: 'Chưa có đo',
      textColor: 'text-slate-400',
    };
  }
  if (kwh < 40) {
    return {
      fill: 'rgba(16, 185, 129, 0.45)', // Emerald
      stroke: '#10b981',
      statusText: 'Tiết kiệm',
      textColor: 'text-emerald-400',
    };
  }
  if (kwh <= 80) {
    return {
      fill: 'rgba(245, 158, 11, 0.45)', // Amber
      stroke: '#f59e0b',
      statusText: 'Trung bình',
      textColor: 'text-amber-400',
    };
  }
  return {
    fill: 'rgba(239, 68, 68, 0.55)', // Red
    stroke: '#ef4444',
    statusText: 'Lãng phí cao',
    textColor: 'text-rose-400',
  };
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

  return (
    <div className="rounded-2xl border border-slate-700/80 bg-slate-900/70 p-6 backdrop-blur-xl shadow-2xl space-y-6">
      {/* Control Bar: Header, Metric Toggle, Stream Status */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b border-slate-800 pb-5">
        <div>
          <div className="flex items-center gap-2.5">
            <h2 className="text-xl font-bold text-white tracking-tight">Sơ đồ Mặt bằng Thời gian thực</h2>
            <span className="rounded-md bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 text-xs font-semibold text-emerald-400">
              Tầng 1
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Mô phỏng 10 khu vực làm việc • Cập nhật tự động qua luồng Server-Sent Events (SSE)
          </p>
        </div>

        {/* Right controls: Toggle & Connection status */}
        <div className="flex flex-wrap items-center gap-3">
          {/* Mode Switcher */}
          <div className="flex items-center rounded-xl bg-slate-800/80 p-1 border border-slate-700/80 shadow-inner">
            <button
              id="mode-toggle-temp"
              onClick={() => setMetricMode('temp')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
                metricMode === 'temp'
                  ? 'bg-gradient-to-r from-emerald-500 to-teal-600 text-white shadow-md'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <Thermometer size={14} />
              <span>Nhiệt độ</span>
            </button>
            <button
              id="mode-toggle-waste"
              onClick={() => setMetricMode('waste')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
                metricMode === 'waste'
                  ? 'bg-gradient-to-r from-amber-500 to-rose-600 text-white shadow-md'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <Zap size={14} />
              <span>Lãng phí</span>
            </button>
          </div>

          {/* Connection Indicator */}
          <div
            id="stream-connection-badge"
            className={`flex items-center gap-2 rounded-xl border px-3 py-1.5 text-xs font-medium transition ${
              isConnected
                ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400'
                : 'border-rose-500/30 bg-rose-500/10 text-rose-400 animate-pulse'
            }`}
            title={isConnected ? 'Đang kết nối live stream' : 'Mất kết nối với SSE server'}
          >
            <span
              className={`h-2 w-2 rounded-full ${
                isConnected ? 'bg-emerald-400 animate-pulse' : 'bg-rose-400'
              }`}
            />
            <Radio size={13} className={isConnected ? 'animate-pulse' : ''} />
            <span>
              {isConnected ? 'Trực tuyến' : `Mất kết nối${retryAttempt > 0 ? ` (thử lại #${retryAttempt})` : ''}`}
            </span>
          </div>
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-400 flex items-center gap-2">
          <Info size={14} />
          <span>Lỗi tải sơ đồ: {error}</span>
        </div>
      )}

      {/* SVG Floor Plan Canvas */}
      <div className="relative rounded-xl border border-slate-800 bg-slate-950/80 p-4 overflow-hidden shadow-inner flex items-center justify-center">
        {loading && (
          <div className="absolute inset-0 bg-slate-950/80 flex items-center justify-center z-10 backdrop-blur-sm text-sm text-slate-300">
            <span className="animate-spin mr-2">⚙️</span> Đang tải sơ đồ mặt bằng...
          </div>
        )}

        <svg
          viewBox="0 0 1010 540"
          className="w-full h-auto max-h-[580px] select-none"
          role="img"
          aria-label="Sơ đồ mặt bằng toà nhà Tầng 1"
        >
          {/* Architectural Outer Boundary Wall */}
          <rect
            x="15"
            y="15"
            width="980"
            height="510"
            rx="16"
            fill="none"
            stroke="#334155"
            strokeWidth="3"
            strokeDasharray="6 4"
          />

          {/* Central Hallway / Atrium Area */}
          <rect
            x="30"
            y="238"
            width="950"
            height="64"
            rx="8"
            fill="rgba(30, 41, 59, 0.4)"
            stroke="#1e293b"
            strokeWidth="1"
          />
          <text
            x="505"
            y="275"
            textAnchor="middle"
            fill="#64748b"
            fontSize="12"
            letterSpacing="3"
            fontWeight="600"
            className="uppercase"
          >
            Hành Lang Trung Tâm • Tầng 1 (Central Corridor)
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

            // Metric values
            const tempVal = reading.outdoor_temperature_c;
            const kwhVal = reading.meter_reading_kwh;

            // Appearance calculations
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
                ? `${kwhVal.toFixed(1)} kWh`
                : '-- kWh';

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
                className="cursor-pointer transition-all duration-300 focus:outline-none group"
              >
                {/* Room Rectangle with reactive gradient fill */}
                <rect
                  x={layout.x}
                  y={layout.y}
                  width={layout.w}
                  height={layout.h}
                  rx="12"
                  fill={style.fill}
                  stroke={style.stroke}
                  strokeWidth="2"
                  className="transition-all duration-500 group-hover:stroke-white group-hover:filter group-hover:drop-shadow-[0_0_12px_rgba(255,255,255,0.2)] group-focus:stroke-white"
                />

                {/* Subtle Room Header Bar */}
                <rect
                  x={layout.x}
                  y={layout.y}
                  width={layout.w}
                  height="34"
                  rx="12"
                  fill="rgba(15, 23, 42, 0.45)"
                />

                {/* Room Name */}
                <text
                  x={layout.x + 14}
                  y={layout.y + 22}
                  fill="#f8fafc"
                  fontSize="12.5"
                  fontWeight="600"
                  className="pointer-events-none"
                >
                  {zoneData.name || layout.label}
                </text>

                {/* Room ID Tag */}
                <text
                  x={layout.x + layout.w - 14}
                  y={layout.y + 22}
                  textAnchor="end"
                  fill="#94a3b8"
                  fontSize="10"
                  fontFamily="monospace"
                  className="pointer-events-none"
                >
                  {layout.id}
                </text>

                {/* Main Metric Value */}
                <text
                  x={layout.x + layout.w / 2}
                  y={layout.y + 95}
                  textAnchor="middle"
                  fill="#ffffff"
                  fontSize="22"
                  fontWeight="bold"
                  className="pointer-events-none filter drop-shadow-sm transition-all duration-300"
                >
                  {displayValue}
                </text>

                {/* Status Badge Box (Dual-indicator: Color + Text a11y) */}
                <rect
                  x={layout.x + layout.w / 2 - 45}
                  y={layout.y + 120}
                  width="90"
                  height="22"
                  rx="6"
                  fill="rgba(15, 23, 42, 0.7)"
                  stroke={style.stroke}
                  strokeWidth="1"
                  className="pointer-events-none"
                />
                <text
                  x={layout.x + layout.w / 2}
                  y={layout.y + 135}
                  textAnchor="middle"
                  fill="#f1f5f9"
                  fontSize="10"
                  fontWeight="500"
                  className="pointer-events-none"
                >
                  {style.statusText}
                </text>

                {/* Call-to-action hint on hover */}
                <text
                  x={layout.x + layout.w / 2}
                  y={layout.y + 162}
                  textAnchor="middle"
                  fill="#38bdf8"
                  fontSize="9.5"
                  fontWeight="500"
                  opacity="0"
                  className="transition-opacity duration-200 group-hover:opacity-100 group-focus:opacity-100 pointer-events-none"
                >
                  🔍 Nhấn xem & hỏi AI →
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      {/* Legend & Guide Bar */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-4 rounded-xl border border-slate-800 bg-slate-900/60 p-4 text-xs">
        <div className="text-slate-400">
          <span className="font-semibold text-slate-200">Ghi chú dải màu ({metricMode === 'temp' ? 'Nhiệt độ' : 'Lãng phí'}):</span>{' '}
          Mỗi khu vực được thể hiện song song qua màu sắc và văn bản trực quan.
        </div>

        {/* Legend Scale */}
        <div className="flex items-center gap-3">
          {metricMode === 'temp' ? (
            <>
              <span className="flex items-center gap-1.5 text-slate-300">
                <span className="h-3 w-3 rounded-full bg-sky-500/80 border border-sky-400" />
                &lt;22°C (Mát)
              </span>
              <span className="flex items-center gap-1.5 text-slate-300">
                <span className="h-3 w-3 rounded-full bg-emerald-500/80 border border-emerald-400" />
                22-25°C (Chuẩn)
              </span>
              <span className="flex items-center gap-1.5 text-slate-300">
                <span className="h-3 w-3 rounded-full bg-amber-500/80 border border-amber-400" />
                25-28°C (Ấm)
              </span>
              <span className="flex items-center gap-1.5 text-slate-300">
                <span className="h-3 w-3 rounded-full bg-rose-500/80 border border-rose-400" />
                &gt;28°C (Nóng)
              </span>
            </>
          ) : (
            <>
              <span className="flex items-center gap-1.5 text-slate-300">
                <span className="h-3 w-3 rounded-full bg-emerald-500/80 border border-emerald-400" />
                &lt;40 kWh (Thấp)
              </span>
              <span className="flex items-center gap-1.5 text-slate-300">
                <span className="h-3 w-3 rounded-full bg-amber-500/80 border border-amber-400" />
                40-80 kWh (Vừa)
              </span>
              <span className="flex items-center gap-1.5 text-slate-300">
                <span className="h-3 w-3 rounded-full bg-rose-500/80 border border-rose-400" />
                &gt;80 kWh (Cao)
              </span>
            </>
          )}
        </div>
      </div>

      {/* Zone Detail Modal Dialog */}
      <ZoneDetailModal
        zone={selectedZone}
        isOpen={Boolean(selectedZone)}
        onClose={() => setSelectedZone(null)}
        onAskCopilot={onAskCopilot}
      />
    </div>
  );
}

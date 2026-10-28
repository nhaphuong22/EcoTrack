import { useEffect } from 'react';
import { X, Bot, Zap, Thermometer, Droplets, Clock, ArrowRight } from 'lucide-react';

export default function ZoneDetailModal({ zone, isOpen, onClose, onAskCopilot }) {
  useEffect(() => {
    function handleKeyDown(e) {
      if (e.key === 'Escape') onClose();
    }
    if (isOpen) {
      window.addEventListener('keydown', handleKeyDown);
    }
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen || !zone) return null;

  const reading = zone.latest_reading || {};
  const temp = Number.isFinite(reading.outdoor_temperature_c)
    ? `${reading.outdoor_temperature_c.toFixed(1)}°C`
    : 'N/A';
  const kwh = Number.isFinite(reading.meter_reading_kwh)
    ? `${reading.meter_reading_kwh.toFixed(1)} kWh`
    : 'N/A';
  const humidity = Number.isFinite(reading.relative_humidity_pct)
    ? `${Math.round(reading.relative_humidity_pct)}%`
    : 'N/A';
  const time = reading.timestamp
    ? new Date(reading.timestamp).toLocaleTimeString('vi-VN', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      })
    : 'Chưa có dữ liệu';

  // State evaluation
  const isHighWaste = reading.meter_reading_kwh > 80;
  const isWarm = reading.outdoor_temperature_c > 26;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="zone-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-md animate-in fade-in duration-200"
    >
      <div
        className="w-full max-w-lg rounded-2xl border border-slate-700/80 bg-gradient-to-b from-slate-900 to-slate-950 p-6 shadow-2xl shadow-black/60 relative space-y-6"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between border-b border-slate-800 pb-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full bg-emerald-400 animate-pulse" />
              <h2 id="zone-modal-title" className="text-xl font-bold text-white">
                {zone.name || `Khu vực ${zone.id}`}
              </h2>
            </div>
            <p className="text-xs text-slate-400 mt-1">
              Mã khu vực: <span className="font-mono text-emerald-400">{zone.id}</span> • Tầng {zone.floor || 1} • EcoTrack Office
            </p>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-white transition"
            aria-label="Đóng bảng chi tiết"
          >
            <X size={20} />
          </button>
        </div>

        {/* 3 Metric Cards */}
        <div className="grid grid-cols-3 gap-3">
          {/* Điện năng */}
          <div className="rounded-xl border border-slate-800/80 bg-slate-800/40 p-3.5 space-y-1">
            <div className="flex items-center gap-1.5 text-xs text-amber-400 font-medium">
              <Zap size={14} />
              <span>Tiêu thụ</span>
            </div>
            <div className="text-lg font-bold text-white">{kwh}</div>
            <div className={`text-[11px] font-medium ${isHighWaste ? 'text-rose-400' : 'text-emerald-400'}`}>
              {isHighWaste ? 'Tải tiêu thụ cao' : 'Mức bình thường'}
            </div>
          </div>

          {/* Nhiệt độ */}
          <div className="rounded-xl border border-slate-800/80 bg-slate-800/40 p-3.5 space-y-1">
            <div className="flex items-center gap-1.5 text-xs text-rose-400 font-medium">
              <Thermometer size={14} />
              <span>Nhiệt độ</span>
            </div>
            <div className="text-lg font-bold text-white">{temp}</div>
            <div className={`text-[11px] font-medium ${isWarm ? 'text-amber-400' : 'text-emerald-400'}`}>
              {isWarm ? 'Hơi ấm' : 'Mát mẻ (Chuẩn)'}
            </div>
          </div>

          {/* Độ ẩm */}
          <div className="rounded-xl border border-slate-800/80 bg-slate-800/40 p-3.5 space-y-1">
            <div className="flex items-center gap-1.5 text-xs text-sky-400 font-medium">
              <Droplets size={14} />
              <span>Độ ẩm</span>
            </div>
            <div className="text-lg font-bold text-white">{humidity}</div>
            <div className="text-[11px] font-medium text-slate-400">Độ ẩm tương đối</div>
          </div>
        </div>

        {/* Time and diagnosis summary */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 space-y-2 text-xs">
          <div className="flex items-center justify-between text-slate-400">
            <span className="flex items-center gap-1">
              <Clock size={12} /> Cập nhật lần cuối:
            </span>
            <span className="font-mono text-slate-200">{time}</span>
          </div>
          <p className="text-slate-300 leading-relaxed">
            {isHighWaste
              ? 'Phòng này đang có dấu hiệu tiêu thụ điện năng vượt mức thông thường. Cần kiểm tra hệ thống chiếu sáng và máy lạnh.'
              : 'Các chỉ số vi khí hậu và năng lượng tại phòng này đang duy trì ở dải vận hành tối ưu.'}
          </p>
        </div>

        {/* Action Button: Hỏi Copilot */}
        <div className="pt-2">
          <button
            id="zone-ask-copilot-btn"
            onClick={() => {
              onClose();
              onAskCopilot(zone);
            }}
            className="w-full flex items-center justify-center gap-2.5 rounded-xl bg-gradient-to-r from-emerald-500 via-teal-500 to-sky-600 px-4 py-3 text-sm font-semibold text-white shadow-lg shadow-emerald-500/20 hover:scale-[1.02] hover:shadow-emerald-500/30 active:scale-[0.98] transition"
          >
            <Bot size={18} />
            <span>Hỏi Copilot phân tích phòng này</span>
            <ArrowRight size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}

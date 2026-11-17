import { useEffect } from 'react';
import { X, Bot, Zap, Thermometer, Droplets, Clock, ArrowRight } from 'lucide-react';

function Reading({ icon: Icon, label, value, note, noteTone = 'text-muted' }) {
  return (
    <div className="bg-panel p-3.5">
      <div className="flex items-center gap-1.5 text-xs font-medium text-muted">
        <Icon size={14} aria-hidden="true" />
        <span>{label}</span>
      </div>
      <div className="num mt-2 text-lg font-semibold text-ink">{value}</div>
      <div className={`mt-1 text-xs font-semibold ${noteTone}`}>{note}</div>
    </div>
  );
}

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
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/55 p-4"
    >
      <div
        className="relative w-full max-w-lg overflow-hidden rounded-md border border-line-strong bg-panel shadow-[0_24px_60px_-20px_rgba(14,30,29,0.55)]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
          <div>
            <h2 id="zone-modal-title" className="text-lg font-bold text-ink">
              {zone.name || `Khu vực ${zone.id}`}
            </h2>
            <p className="meta mt-1">
              Mã khu vực: <span className="num font-medium text-ink-2">{zone.id}</span> • Tầng {zone.floor || 1} • EcoTrack Office
            </p>
          </div>
          <button
            onClick={onClose}
            className="btn btn-quiet btn-sm px-2"
            aria-label="Đóng bảng chi tiết"
          >
            <X size={16} aria-hidden="true" />
          </button>
        </div>

        <div className="space-y-4 p-5">
          <div className="grid grid-cols-3 gap-px overflow-hidden rounded border border-line bg-line">
            <Reading
              icon={Zap}
              label="Tiêu thụ"
              value={kwh}
              note={isHighWaste ? 'Tải tiêu thụ cao' : 'Mức bình thường'}
              noteTone={isHighWaste ? 'text-crit' : 'text-ok'}
            />
            <Reading
              icon={Thermometer}
              label="Nhiệt độ"
              value={temp}
              note={isWarm ? 'Hơi ấm' : 'Mát mẻ (Chuẩn)'}
              noteTone={isWarm ? 'text-warn' : 'text-ok'}
            />
            <Reading icon={Droplets} label="Độ ẩm" value={humidity} note="Độ ẩm tương đối" />
          </div>

          <div className="rounded border border-line bg-sunken p-4 text-sm">
            <div className="flex items-center justify-between text-xs text-muted">
              <span className="flex items-center gap-1.5">
                <Clock size={12} aria-hidden="true" /> Cập nhật lần cuối:
              </span>
              <span className="num font-medium text-ink">{time}</span>
            </div>
            <p className="mt-3 leading-relaxed text-ink-2">
              {isHighWaste
                ? 'Phòng này đang có dấu hiệu tiêu thụ điện năng vượt mức thông thường. Cần kiểm tra hệ thống chiếu sáng và máy lạnh.'
                : 'Các chỉ số vi khí hậu và năng lượng tại phòng này đang duy trì ở dải vận hành tối ưu.'}
            </p>
          </div>

          <button
            id="zone-ask-copilot-btn"
            onClick={() => {
              onClose();
              onAskCopilot(zone);
            }}
            className="btn btn-primary w-full gap-2.5 py-3"
          >
            <Bot size={17} aria-hidden="true" />
            <span>Hỏi Copilot phân tích phòng này</span>
            <ArrowRight size={16} aria-hidden="true" />
          </button>
        </div>
      </div>
    </div>
  );
}

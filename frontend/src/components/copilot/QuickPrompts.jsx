import { Zap, Bot, CheckSquare } from 'lucide-react';

const QUICK_PROMPTS = [
  { icon: '📊', label: 'Tổng quan năng lượng', msg: 'Cho tôi xem báo cáo tổng quan tiêu thụ điện và chỉ số quan trọng nhất.' },
  { icon: '⚠️', label: 'Phân tích sự cố mới nhất', msg: 'Phân tích và chẩn đoán sự cố bất thường gần nhất được phát hiện.' },
  { icon: '📈', label: 'Dự báo phụ tải 24h', msg: 'Dự báo phụ tải điện 24 giờ tới và đề xuất tối ưu giờ cao điểm.' },
  { icon: '💡', label: 'Khuyến nghị tiết kiệm điện', msg: 'Đề xuất các biện pháp cụ thể giúp giảm chi phí điện năng tháng này.' },
];

export default function QuickPrompts({ onSelect, disabled }) {
  return (
    <div className="space-y-1.5">
      <p className="text-[11px] uppercase tracking-widest text-slate-500 px-1">Gợi ý nhanh</p>
      {QUICK_PROMPTS.map((p) => (
        <button
          key={p.label}
          id={`quick-prompt-${p.label.replace(/\s+/g, '-').toLowerCase()}`}
          onClick={() => onSelect(p.msg)}
          disabled={disabled}
          className="flex w-full items-center gap-2.5 rounded-lg border border-slate-700/60 bg-slate-800/50 px-3 py-2 text-left text-xs text-slate-300 transition hover:border-emerald-500/40 hover:bg-emerald-500/5 hover:text-emerald-300 disabled:opacity-40"
        >
          <span className="text-base leading-none">{p.icon}</span>
          <span className="truncate">{p.label}</span>
        </button>
      ))}
    </div>
  );
}

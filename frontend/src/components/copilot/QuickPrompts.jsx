import { BarChart3, AlertTriangle, TrendingUp, Lightbulb } from 'lucide-react';

const QUICK_PROMPTS = [
  { icon: BarChart3, label: 'Tổng quan năng lượng', msg: 'Cho tôi xem báo cáo tổng quan tiêu thụ điện và chỉ số quan trọng nhất.' },
  { icon: AlertTriangle, label: 'Phân tích sự cố mới nhất', msg: 'Phân tích và chẩn đoán sự cố bất thường gần nhất được phát hiện.' },
  { icon: TrendingUp, label: 'Dự báo phụ tải 24h', msg: 'Dự báo phụ tải điện 24 giờ tới và đề xuất tối ưu giờ cao điểm.' },
  { icon: Lightbulb, label: 'Khuyến nghị tiết kiệm điện', msg: 'Đề xuất các biện pháp cụ thể giúp giảm chi phí điện năng tháng này.' },
];

export default function QuickPrompts({ onSelect, disabled }) {
  return (
    <div>
      <p className="mb-2 text-xs font-semibold text-muted">Gợi ý nhanh</p>
      <div className="flex flex-wrap gap-2">
        {QUICK_PROMPTS.map(({ icon: Icon, label, msg }) => (
          <button
            key={label}
            id={`quick-prompt-${label.replace(/\s+/g, '-').toLowerCase()}`}
            onClick={() => onSelect(msg)}
            disabled={disabled}
            className="btn btn-quiet btn-sm gap-1.5 font-medium"
          >
            <Icon size={13} className="text-muted" aria-hidden="true" />
            <span>{label}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

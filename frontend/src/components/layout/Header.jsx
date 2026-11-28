import { Menu, RefreshCw } from 'lucide-react';

const TIME_RANGES = [
  { value: 24, label: '24 giờ' },
  { value: 168, label: '7 ngày' },
  { value: 720, label: '30 ngày' },
];

export default function Header({
  title = 'Tổng quan Năng lượng',
  badge = null,
  updatedLabel = null,
  onRefresh,
  loading,
  timeRange = 168,
  onTimeRangeChange,
  showTimeRange = true,
  onOpenMobileNav,
  rightSlot = null,
}) {
  return (
    <header className="sticky top-0 z-20 border-b border-line bg-white/95 backdrop-blur-sm">
      <div className="mx-auto flex max-w-screen-2xl flex-wrap items-center justify-between gap-x-4 gap-y-2.5 px-4 py-3 sm:px-6 lg:px-8">
        <div className="flex min-w-0 items-center gap-3">
          {onOpenMobileNav && (
            <button
              type="button"
              onClick={onOpenMobileNav}
              className="btn btn-quiet btn-sm h-9 px-2.5 lg:hidden"
              aria-label="Mở menu điều hướng"
              title="Mở menu"
            >
              <Menu size={16} aria-hidden="true" />
            </button>
          )}

          <div className="flex flex-wrap items-center gap-2.5">
            <h1 className="truncate text-lg font-bold tracking-tight text-ink sm:text-xl">
              {title}
            </h1>
            {badge}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          {rightSlot}

          {updatedLabel && (
            <span className="num hidden rounded-xl border border-line bg-sunken px-3 py-1.5 text-xs font-medium text-muted xl:inline-flex">
              Cập nhật lúc {updatedLabel}
            </span>
          )}

          {showTimeRange && onTimeRangeChange && (
            <div
              role="group"
              aria-label="Khoảng thời gian hiển thị"
              className="inline-flex items-center rounded-xl border border-line bg-sunken p-1"
            >
              {TIME_RANGES.map((opt) => {
                const active = timeRange === opt.value;
                return (
                  <button
                    key={opt.value}
                    type="button"
                    aria-pressed={active}
                    onClick={() => onTimeRangeChange(opt.value)}
                    className={`rounded-lg px-2.5 py-1 text-xs font-semibold transition-colors ${
                      active
                        ? 'bg-white text-ink shadow-sm'
                        : 'text-muted hover:text-ink'
                    }`}
                  >
                    {opt.label}
                  </button>
                );
              })}
            </div>
          )}

          {onRefresh && (
            <button
              id="header-refresh-btn"
              type="button"
              onClick={onRefresh}
              disabled={loading}
              className="btn btn-quiet btn-sm h-9 px-3"
              title="Cập nhật dữ liệu"
              aria-label="Cập nhật dữ liệu"
            >
              <RefreshCw size={14} className={loading ? 'animate-spin' : ''} aria-hidden="true" />
              <span className="hidden sm:inline">Cập nhật</span>
            </button>
          )}
        </div>
      </div>
    </header>
  );
}

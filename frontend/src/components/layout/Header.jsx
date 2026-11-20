import { RefreshCw, Building2 } from 'lucide-react';

// Workspace bar: which building you are looking at, tabs for the work areas, refresh.
export default function Header({ onRefresh, loading, children }) {
  return (
    <div className="border-b border-line bg-panel">
      <div className="mx-auto flex max-w-screen-2xl flex-wrap items-end justify-between gap-x-6 gap-y-3 px-4 pt-4 sm:px-6 lg:px-8">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 pb-0">
          <div className="flex items-center gap-2 pb-3">
            <Building2 size={16} className="text-muted" aria-hidden="true" />
            <span className="text-sm font-semibold text-ink">Office Tower 01</span>
            <span className="chip chip-ok">
              <span className="h-1.5 w-1.5 rounded-full bg-ok" aria-hidden="true" />
              Trực tuyến
            </span>
          </div>
          {children}
        </div>

        <button
          id="header-refresh-btn"
          onClick={onRefresh}
          disabled={loading}
          className="btn btn-quiet btn-sm mb-3"
          title="Refresh data"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} aria-hidden="true" />
          <span>Cập nhật</span>
        </button>
      </div>
    </div>
  );
}

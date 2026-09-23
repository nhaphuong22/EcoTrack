import { Zap, RefreshCw, Building2 } from 'lucide-react';

export default function Header({ onRefresh, loading }) {
  return (
    <header className="sticky top-0 z-30 border-b border-slate-700/60 bg-slate-900/90 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-screen-2xl items-center justify-between px-6">
        {/* Brand */}
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-emerald-500 to-teal-600 shadow-lg shadow-emerald-500/20">
            <Zap size={18} className="text-white" />
          </div>
          <div>
            <span className="text-lg font-bold tracking-tight text-white">Eco</span>
            <span className="text-lg font-bold tracking-tight text-emerald-400">Track</span>
            <span className="ml-2 hidden rounded bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-emerald-400 sm:inline">
              AI Analytics
            </span>
          </div>
        </div>

        {/* Centre: Building selector */}
        <div className="flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-800/60 px-3 py-1.5">
          <Building2 size={14} className="text-slate-400" />
          <span className="text-sm font-medium text-slate-200">Office Tower 01</span>
          <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" title="Live" />
        </div>

        {/* Right: Refresh */}
        <button
          id="header-refresh-btn"
          onClick={onRefresh}
          disabled={loading}
          className="flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-800/60 px-3 py-1.5 text-sm text-slate-300 transition hover:border-emerald-500/50 hover:bg-emerald-500/10 hover:text-emerald-400 disabled:opacity-40"
          title="Refresh data"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          <span className="hidden sm:inline">Cập nhật</span>
        </button>
      </div>
    </header>
  );
}

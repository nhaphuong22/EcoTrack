import { useEffect } from 'react';
import { Building2, ArrowLeft, LogOut, X } from 'lucide-react';
import BrandMark from './BrandMark';

const ROLE_LABELS = {
  ADMIN: 'Quản trị viên',
  MANAGER: 'Quản lý tòa nhà',
  TECHNICIAN: 'Kỹ thuật viên',
};

function getInitials(name) {
  if (!name) return 'ET';
  const parts = String(name).trim().split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
}

export default function Sidebar({
  subtitle = 'Quản lý năng lượng',
  contextTitle = 'Tòa nhà Văn phòng 01',
  contextStatus = 'Đang trực tuyến',
  user = null,
  defaultRoleLabel = 'Vận hành',
  onBackToPortal = null,
  onLogout = null,
  accountActions = null,
  mobileOpen = false,
  onCloseMobile,
  children,
}) {
  useEffect(() => {
    if (!mobileOpen) return undefined;
    const onKeyDown = (e) => {
      if (e.key === 'Escape') onCloseMobile?.();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [mobileOpen, onCloseMobile]);

  const roleLabel = user?.role ? ROLE_LABELS[user.role] || defaultRoleLabel : defaultRoleLabel;
  const showAccountSection = Boolean(user || onBackToPortal || onLogout || accountActions);

  return (
    <>
      {mobileOpen && (
        <div
          className="fixed inset-0 z-30 bg-ink/40 backdrop-blur-[1px] lg:hidden"
          onClick={onCloseMobile}
          aria-hidden="true"
        />
      )}

      <div
        className={`fixed inset-y-0 left-0 z-40 flex w-64 shrink-0 flex-col border-r border-line bg-panel transition-transform duration-200 ease-out lg:sticky lg:top-0 lg:z-10 lg:h-screen lg:translate-x-0 ${
          mobileOpen ? 'translate-x-0 shadow-[16px_0_40px_-16px_rgba(14,30,29,0.28)]' : '-translate-x-full'
        }`}
      >
        <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-4">
          <div className="flex items-center gap-2.5">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-shell text-white shadow-sm">
              <BrandMark size={19} />
            </span>
            <div>
              <span className="block text-base font-bold leading-tight tracking-tight text-ink">
                EcoTrack
              </span>
              <span className="block text-[11px] font-medium text-muted">
                {subtitle}
              </span>
            </div>
          </div>

          <button
            type="button"
            onClick={onCloseMobile}
            className="btn btn-quiet btn-sm px-2 lg:hidden"
            aria-label="Đóng thanh điều hướng"
          >
            <X size={15} aria-hidden="true" />
          </button>
        </div>

        {contextTitle && (
          <div className="px-4 pt-4">
            <div className="rounded-xl border border-line bg-sunken/80 px-3.5 py-2.5">
              <div className="flex items-center gap-2 text-xs font-semibold text-ink">
                <Building2 size={14} className="shrink-0 text-shell" aria-hidden="true" />
                <span className="truncate">{contextTitle}</span>
              </div>
              {contextStatus && (
                <p className="mt-1 flex items-center gap-1.5 pl-5 text-[11px] font-medium text-ok">
                  <span className="h-1.5 w-1.5 rounded-full bg-ok" aria-hidden="true" />
                  {contextStatus}
                </p>
              )}
            </div>
          </div>
        )}

        <nav
          aria-label="Điều hướng chính"
          className="flex-1 overflow-y-auto px-4 py-4"
          onClick={() => {
            if (mobileOpen) onCloseMobile?.();
          }}
        >
          {children}
        </nav>

        {showAccountSection && (
          <div className="space-y-2.5 border-t border-line bg-sunken/40 p-4">
            {user && (
              <div className="flex items-center gap-2.5 px-1">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-ok-bg text-xs font-bold text-ok">
                  {getInitials(user.name)}
                </span>
                <div className="min-w-0">
                  <p className="truncate text-xs font-semibold text-ink">
                    {user.name || 'Người dùng'}
                  </p>
                  {roleLabel && (
                    <p className="truncate text-[11px] text-muted">{roleLabel}</p>
                  )}
                </div>
              </div>
            )}

            {(accountActions || onBackToPortal || onLogout) && (
              <div className="space-y-1.5">
                {accountActions}
                {onBackToPortal && (
                  <button
                    type="button"
                    onClick={onBackToPortal}
                    className="btn btn-quiet btn-sm w-full justify-start"
                  >
                    <ArrowLeft size={14} aria-hidden="true" />
                    <span>Về cổng cư dân</span>
                  </button>
                )}
                {onLogout && (
                  <button
                    type="button"
                    onClick={onLogout}
                    className="btn btn-quiet btn-sm w-full justify-start text-crit hover:bg-crit-bg/50"
                  >
                    <LogOut size={14} aria-hidden="true" />
                    <span>Đăng xuất</span>
                  </button>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </>
  );
}

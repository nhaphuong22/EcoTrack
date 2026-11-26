import { useState, useEffect, useCallback, useRef, lazy, Suspense } from 'react';
import {
  Zap,
  Clock,
  AlertTriangle,
  CheckCircle2,
  Lock,
  Send,
  Sparkles,
  UserPlus,
  Users,
  LayoutDashboard,
  Link2,
  Activity,
  MapPin,
  Building2,
  ArrowRight,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { accountApi, API_BASE_URL } from './services/api';
import Sidebar from './components/layout/Sidebar';
import Header from './components/layout/Header';
import BrandMark from './components/layout/BrandMark';
import PortalSparkline from './components/portal/PortalSparkline';

const field = 'field';
const button = 'btn btn-primary';
const AdminDashboard = lazy(() => import('./App'));

function message(error) {
  const detail = error.response?.data?.detail;
  return typeof detail === 'string'
    ? detail
    : Array.isArray(detail)
    ? detail.map((item) => item.msg).join('; ')
    : 'Không thể kết nối. Vui lòng thử lại.';
}

const labelOf = (context) =>
  context.scope === 'household'
    ? context.label
    : `${context.label} — ${context.scope === 'common' ? 'Khu vực chung' : 'Tổng tòa nhà'}`;

const formatKwh = (value) => (value > 0 && value < 1 ? value.toFixed(4) : value.toFixed(2));

const SEVERITY_MAP = {
  CRITICAL: { label: 'Nghiêm trọng', chip: 'chip-crit' },
  MEDIUM: { label: 'Trung bình', chip: 'chip-warn' },
  LOW: { label: 'Thấp', chip: 'chip-mute' },
  NORMAL: { label: 'Bình thường', chip: 'chip-ok' },
};

const QUICK_QUESTIONS = [
  'Tổng điện năng hiện tại là bao nhiêu?',
  'Phạm vi này có cảnh báo nào không?',
];

export default function AccountPortal() {
  const [user, setUser] = useState(null);
  const [adminDashboard, setAdminDashboard] = useState(() => window.location.pathname === '/dashboard');
  const [checking, setChecking] = useState(true);
  const [register, setRegister] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [googleError, setGoogleError] = useState('');
  const [buildings, setBuildings] = useState([]);
  const [managedContexts, setManagedContexts] = useState([]);
  const [selection, setSelection] = useState('');
  const [data, setData] = useState(null);
  const [zones, setZones] = useState([]);
  const [invite, setInvite] = useState('');
  const [chat, setChat] = useState([]);
  const [chatId, setChatId] = useState(null);
  const [chatInput, setChatInput] = useState('');
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [activeSection, setActiveSection] = useState('overview');
  const [activityTab, setActivityTab] = useState('anomalies'); // 'anomalies' | 'history'
  const [showAllAnomalies, setShowAllAnomalies] = useState(false);
  const version = useRef(0);
  const [inviteNotice, setInviteNotice] = useState('');
  const navigateTo = useCallback((path, replace = false) => {
    window.history[replace ? 'replaceState' : 'pushState']({}, '', path);
    setAdminDashboard(path === '/dashboard');
  }, []);

  useEffect(() => {
    const handlePopState = () => setAdminDashboard(window.location.pathname === '/dashboard');
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);
  useEffect(() => {
    const url = new URL(window.location.href);
    const invited = url.searchParams.get('invite_token');
    if (invited && /^[a-f0-9]{64}$/.test(invited.trim())) {
      // Arrived from the invitation email: prefill the code and let the
      // resident confirm, so the link alone never joins a household.
      setInvite(invited.trim());
      setInviteNotice('Đã nhận liên kết lời mời. Hãy đăng nhập bằng email được mời rồi bấm "Nhận lời mời".');
      url.searchParams.delete('invite_token');
      window.history.replaceState({}, '', url.toString());
    }
    const code = url.searchParams.get('auth_error');
    if (code) {
      setGoogleError(
        code === 'google_link_required'
          ? 'Email này đã có tài khoản. Hãy đăng nhập bằng mật khẩu, sau đó chọn Liên kết Google.'
          : 'Đăng nhập Google chưa thành công. Vui lòng thử lại.'
      );
      url.searchParams.delete('auth_error');
      window.history.replaceState({}, '', url.toString());
    }
  }, []);

  const recordManagement = useCallback((buildingId, units) => {
    const next = units.flatMap((unit) =>
      unit.households
        .filter((household) => !household.ends_at)
        .map((household) => ({
          key: `household:${household.id}`,
          scope: 'household',
          household_id: household.id,
          building_id: buildingId,
          label: `Căn ${unit.code} — ${household.name} (quản lý)`,
        }))
    );
    setManagedContexts((previous) => {
      const updated = [...previous.filter((item) => item.building_id !== buildingId), ...next];
      return JSON.stringify(updated) === JSON.stringify(previous) ? previous : updated;
    });
  }, []);

  const reloadIdentity = useCallback(async () => {
    try {
      const response = await accountApi.get('/api/v1/auth/me');
      setUser(response.data.user);
      const result = await accountApi.get('/api/v1/portal/buildings');
      setBuildings(result.data.buildings);
    } catch (err) {
      if (err.response?.status === 401) {
        setUser(null);
        setData(null);
        setBuildings([]);
      } else {
        throw err;
      }
    }
  }, []);

  useEffect(() => {
    reloadIdentity()
      .catch((err) => setError(message(err)))
      .finally(() => setChecking(false));
  }, [reloadIdentity]);

  useEffect(() => {
    if (!checking && adminDashboard && !user?.role) navigateTo('/', true);
  }, [adminDashboard, checking, navigateTo, user?.role]);

  const contexts = [
    ...new Map(
      [
        ...(user?.households || []).map((household) => ({
          key: `household:${household.id}`,
          scope: 'household',
          household_id: household.id,
          building_id: household.unit.building_id,
          label: `${household.unit.building.name} — Căn ${household.unit.code} — ${household.name}`,
        })),
        ...managedContexts.filter(
          (item) =>
            user?.is_platform_admin ||
            user?.staff.some((staff) => staff.building_id === item.building_id)
        ),
        ...buildings.flatMap((building) =>
          ['building', 'common'].map((scope) => ({
            key: `${scope}:${building.id}`,
            building_id: building.id,
            scope,
            label: building.name,
          }))
        ),
      ].map((item) => [item.key, item])
    ).values(),
  ];
  const context = contexts.find((item) => item.key === selection);
  const contextKey = contexts.map((item) => item.key).join('|');

  useEffect(() => {
    if (!contexts.some((item) => item.key === selection)) {
      setSelection(contexts[0]?.key || '');
      setData(null);
      setZones([]);
    }
  }, [contextKey, selection]);

  useEffect(() => {
    const current = ++version.current;
    setData(null);
    setZones([]);
    setChat([]);
    setChatId(null);
    setShowAllAnomalies(false);
    if (!context || !user || adminDashboard) return;
    setError('');
    const params = {
      scope: context.scope,
      building_id: context.building_id,
      ...(context.household_id ? { household_id: context.household_id } : {}),
    };
    let disposed = false;
    let refreshTimer;

    async function load() {
      try {
        const [overview, rooms] = await Promise.all([
          accountApi.get('/api/v1/portal/overview', { params }),
          accountApi.get('/api/v1/portal/zones', { params }),
        ]);
        if (!disposed && current === version.current) {
          setData(overview.data);
          setZones(rooms.data.zones);
          setError('');
          if (!overview.data?.anomalies?.length && overview.data?.data?.length) {
            setActivityTab('history');
          } else {
            setActivityTab('anomalies');
          }
        }
      } catch (err) {
        if (disposed || current !== version.current) return;
        setData(null);
        setZones([]);
        setError(message(err));
        if ([401, 403].includes(err.response?.status)) await reloadIdentity().catch(() => {});
      }
    }

    load();
    const source =
      typeof EventSource !== 'undefined'
        ? new EventSource(
            `${API_BASE_URL}/api/v1/portal/stream?${new URLSearchParams(params)}`,
            { withCredentials: true }
          )
        : null;
    source?.addEventListener('reading', () => {
      if (!refreshTimer) refreshTimer = setTimeout(() => { refreshTimer = null; load(); }, 500);
    });
    if (source) {
      source.onerror = () => {
        if (!disposed) {
          setData(null);
          setZones([]);
          reloadIdentity().catch(() => {});
        }
      };
      source.onopen = () => {
        if (!disposed) load();
      };
    }
    return () => {
      disposed = true;
      clearTimeout(refreshTimer);
      source?.close();
    };
  }, [selection, contextKey, user?.id, adminDashboard, reloadIdentity]);

  async function authenticate(event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    setGoogleError('');
    const values = Object.fromEntries(new FormData(event.currentTarget));
    try {
      await accountApi.post(`/api/v1/auth/${register ? 'register' : 'login'}`, values);
      await reloadIdentity();
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }

  async function acceptInvitation(event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      await accountApi.post('/api/v1/portal/invitations/accept', { token: invite.trim() });
      setInvite('');
      setInviteNotice('');
      await reloadIdentity();
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }

  async function logout() {
    try {
      await accountApi.post('/api/v1/auth/logout');
      version.current += 1;
      setUser(null);
      setData(null);
      setZones([]);
      setSelection('');
      setBuildings([]);
      setManagedContexts([]);
      setChat([]);
      setGoogleError('');
      navigateTo('/', true);
    } catch (err) {
      setError(message(err));
    }
  }

  async function sendQuestion(questionText) {
    const trimmed = String(questionText || '').trim();
    if (!trimmed || !context) return;
    const current = version.current;
    setBusy(true);
    setError('');
    setChatInput('');
    try {
      const response = await accountApi.post('/api/v1/portal/chat', {
        message: trimmed,
        scope: context.scope,
        building_id: context.building_id,
        household_id: context.household_id,
        session_id: chatId || undefined,
      });
      if (current !== version.current) return;
      setChatId(response.data.session_id);
      setChat((previous) => [...previous, { question: trimmed, answer: response.data.reply }]);
    } catch (err) {
      if (current === version.current) setError(message(err));
    } finally {
      setBusy(false);
    }
  }

  async function ask(event) {
    event.preventDefault();
    const input = new FormData(event.currentTarget).get('message');
    event.currentTarget.reset();
    await sendQuestion(input);
  }

  const jumpTo = (section, id, tab) => {
    setActiveSection(section);
    if (tab) setActivityTab(tab);
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  if (checking) {
    return (
      <main className="grid min-h-screen place-items-center bg-ground text-sm text-muted">
        Đang kiểm tra phiên đăng nhập…
      </main>
    );
  }

  // Any operator role (ADMIN, MANAGER, TECHNICIAN) may open the operations dashboard; residents have no role.
  if (user?.role && adminDashboard) {
    return (
      <Suspense fallback={<p className="min-h-screen bg-ground p-8 text-sm text-muted">Đang tải bảng điều khiển…</p>}>
        <AdminDashboard
          user={user}
          onBackToPortal={() => navigateTo('/')}
          onLogout={logout}
        />
      </Suspense>
    );
  }

  if (!user) {
    return (
      <main className="min-h-screen bg-ground lg:grid lg:grid-cols-[5fr_6fr]">
        <div className="flex flex-col justify-between gap-10 bg-shell px-6 py-8 text-shell-ink sm:px-10 lg:min-h-screen lg:px-14 lg:py-12">
          <div className="flex items-center gap-3 text-white">
            <BrandMark size={34} />
            <h1 className="text-2xl font-bold tracking-tight">EcoTrack</h1>
          </div>
          <FloorPlanArt />
          <div className="space-y-3">
            <p className="max-w-md text-lg font-semibold leading-snug text-white">
              Điện năng từng khu vực, cảnh báo bất thường và trợ lý hỏi đáp trong một cổng.
            </p>
            <p className="text-sm text-shell-muted">
              Năng lượng cư dân · Theo dõi theo thời gian thực · Quyền truy cập theo hộ gia đình
            </p>
          </div>
        </div>

        <div className="flex items-center justify-center px-4 py-10 sm:px-8">
          <section className="panel w-full max-w-md p-7 sm:p-8">
            <h2 className="mb-6 text-2xl font-bold text-ink">
              {register ? 'Đăng ký tài khoản' : 'Đăng nhập'}
            </h2>
            {(error || googleError) && (
              <p role="alert" className="mb-5 rounded-xl border border-crit/30 bg-crit-bg p-3 text-sm text-crit">
                {error || googleError}
              </p>
            )}
            <a
              className="btn btn-quiet w-full py-3"
              href={`${API_BASE_URL}/api/v1/auth/google/start`}
            >
              Tiếp tục bằng Google
            </a>
            <div className="my-5 flex items-center gap-3 text-xs text-muted" aria-hidden="true">
              <span className="h-px flex-1 bg-line-strong" />
              hoặc dùng email
              <span className="h-px flex-1 bg-line-strong" />
            </div>
            <form onSubmit={authenticate} className="space-y-4">
              {register && (
                <label className="block">
                  <span className="field-label">Họ tên</span>
                  <input name="name" required maxLength={100} autoComplete="name" className={field} />
                </label>
              )}
              <label className="block">
                <span className="field-label">Email</span>
                <input name="email" type="email" required maxLength={254} autoComplete="email" className={field} />
              </label>
              <label className="block">
                <span className="field-label">Mật khẩu</span>
                <input
                  name="password"
                  type="password"
                  required
                  minLength={10}
                  maxLength={128}
                  autoComplete={register ? 'new-password' : 'current-password'}
                  className={field}
                />
              </label>
              {register && (
                <p className="text-sm text-muted">
                  Ít nhất 10 ký tự. Sau khi đăng ký, nhập mã mời để tham gia hộ gia đình.
                </p>
              )}
              <button className={`${button} w-full py-3`} disabled={busy}>
                {busy ? 'Đang xử lý…' : register ? 'Đăng ký' : 'Đăng nhập'}
              </button>
            </form>
            <button
              className="link mt-5 text-sm"
              onClick={() => {
                setRegister(!register);
                setError('');
              }}
            >
              {register ? 'Đã có tài khoản? Đăng nhập' : 'Chưa có tài khoản? Đăng ký'}
            </button>
          </section>
        </div>
      </main>
    );
  }

  const isManager =
    context &&
    (user.is_platform_admin || user.staff.some((item) => item.building_id === context.building_id));
  const ownerHouseholds = user.households?.filter((household) => household.role === 'OWNER') || [];

  const anomalyCount = data?.anomalies?.length ?? 0;
  const visibleAnomalies = showAllAnomalies
    ? data?.anomalies || []
    : (data?.anomalies || []).slice(0, 6);
  const recentHistory = (data?.data || []).slice(-24).reverse();

  const scopeBadgeText = !contexts.length
    ? 'Chưa gán hộ gia đình'
    : context?.scope === 'household'
    ? 'Phạm vi hộ gia đình'
    : context?.scope === 'common'
    ? 'Khu vực chung'
    : 'Tổng tòa nhà';

  const navLinkClass = (active) =>
    `flex w-full items-center gap-2.5 rounded-xl px-3.5 py-2.5 text-left text-sm font-semibold transition-colors ${
      active
        ? 'bg-shell text-white shadow-sm'
        : 'text-ink-2 hover:bg-sunken hover:text-ink'
    }`;

  return (
    <div className="flex min-h-screen">
      <Sidebar
        subtitle="Năng lượng cư dân"
        contextTitle={context?.label || 'Cổng thông tin cư dân'}
        contextStatus={scopeBadgeText}
        user={user}
        defaultRoleLabel="Cư dân"
        onLogout={logout}
        mobileOpen={mobileNavOpen}
        onCloseMobile={() => setMobileNavOpen(false)}
        accountActions={
          <>
            {user.role && (
              <button
                type="button"
                className="btn btn-primary btn-sm w-full justify-start"
                onClick={() => navigateTo('/dashboard')}
              >
                <LayoutDashboard size={14} aria-hidden="true" />
                <span>Dashboard hệ thống</span>
              </button>
            )}
            {!user.google_linked && (
              <a
                className="btn btn-quiet btn-sm w-full justify-start"
                href={`${API_BASE_URL}/api/v1/auth/google/start`}
              >
                <Link2 size={14} aria-hidden="true" />
                <span>Liên kết Google</span>
              </a>
            )}
          </>
        }
      >
        <div className="space-y-1">
          <button
            type="button"
            onClick={() => jumpTo('overview', 'portal-summary')}
            className={navLinkClass(activeSection === 'overview')}
          >
            <Zap size={16} aria-hidden="true" />
            <span>Tổng quan</span>
          </button>

          {contexts.length > 0 && (
            <>
              {(!!zones.length || (data?.data?.length ?? 0) > 1) && (
                <button
                  type="button"
                  onClick={() => jumpTo('zones', 'portal-zones')}
                  className={navLinkClass(activeSection === 'zones')}
                >
                  <MapPin size={16} aria-hidden="true" />
                  <span>Khu vực được phép xem</span>
                </button>
              )}

              <button
                type="button"
                onClick={() => jumpTo('anomalies', 'portal-activity', 'anomalies')}
                className={navLinkClass(activeSection === 'anomalies')}
              >
                <AlertTriangle size={16} aria-hidden="true" />
                <span>Cảnh báo bất thường</span>
              </button>

              <button
                type="button"
                onClick={() => jumpTo('history', 'portal-activity', 'history')}
                className={navLinkClass(activeSection === 'history')}
              >
                <Activity size={16} aria-hidden="true" />
                <span>Lịch sử gần nhất</span>
              </button>

              {isManager && (
                <button
                  type="button"
                  onClick={() => jumpTo('management', 'portal-management')}
                  className={navLinkClass(activeSection === 'management')}
                >
                  <Building2 size={16} aria-hidden="true" />
                  <span>Quản lý căn hộ</span>
                </button>
              )}
            </>
          )}
        </div>
      </Sidebar>

      <div className="flex min-w-0 flex-1 flex-col">
        <Header
          title="Năng lượng cư dân"
          badge={
            contexts.length > 0 ? (
              <span className="chip chip-ok">
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-ok" aria-hidden="true" />
                Tự cập nhật khi có số đo mới
              </span>
            ) : null
          }
          showTimeRange={false}
          onOpenMobileNav={() => setMobileNavOpen(true)}
          rightSlot={
            contexts.length > 0 ? (
              <label className="flex w-full items-center gap-2 sm:w-auto">
                <span className="hidden text-xs font-medium text-muted xl:inline">
                  Phạm vi xem dữ liệu
                </span>
                <select
                  aria-label="Phạm vi xem dữ liệu"
                  className="field h-9 w-full min-w-[210px] py-1 text-xs font-medium sm:w-auto sm:max-w-xs"
                  value={selection}
                  onChange={(event) => {
                    setData(null);
                    setZones([]);
                    setSelection(event.target.value);
                  }}
                >
                  {contexts.map((item) => (
                    <option key={item.key} value={item.key}>
                      {labelOf(item)}
                    </option>
                  ))}
                </select>
              </label>
            ) : null
          }
        />

        <main className="mx-auto w-full max-w-screen-2xl flex-1 space-y-5 px-4 py-6 sm:px-6 lg:px-8">
          {(error || googleError) && (
            <p
              role="alert"
              className="rounded-2xl border border-crit/30 bg-crit-bg px-4 py-3 text-sm text-crit"
            >
              {error || googleError}
            </p>
          )}

          {!contexts.length && (
            <div className="mx-auto grid max-w-3xl gap-5">
              <div className="panel p-5 text-sm text-ink-2">
                Tài khoản chưa thuộc hộ gia đình nào. Hãy nhận mã mời từ quản lý hoặc chủ hộ.
              </div>
              <InviteForm
                invite={invite}
                setInvite={setInvite}
                busy={busy}
                onSubmit={acceptInvitation}
                notice={inviteNotice}
              />
            </div>
          )}

          {contexts.length > 0 && (
            <>
              {context && (
                <section
                  id="portal-summary"
                  aria-label="Tóm tắt"
                  className="grid grid-cols-1 gap-4 sm:grid-cols-3"
                >
                  <article className="panel flex flex-col justify-between p-5">
                    <div className="flex items-start justify-between gap-3">
                      <h2 className="text-[13px] font-medium text-muted">
                        Điện năng trong khoảng dữ liệu
                      </h2>
                      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-ok-bg text-ok">
                        <Zap size={17} aria-hidden="true" />
                      </span>
                    </div>
                    <p className="num mt-3 text-[28px] font-bold leading-none text-ink">
                      {data ? `${formatKwh(data.metrics.total_consumption_kwh)} kWh` : '—'}
                    </p>
                    <p className="mt-3 text-xs text-muted">
                      Tổng tiêu thụ trong phạm vi được phép xem
                    </p>
                  </article>

                  <article className="panel flex flex-col justify-between p-5">
                    <div className="flex items-start justify-between gap-3">
                      <h2 className="text-[13px] font-medium text-muted">
                        Số thời điểm có dữ liệu
                      </h2>
                      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-sunken text-shell">
                        <Clock size={17} aria-hidden="true" />
                      </span>
                    </div>
                    <p className="num mt-3 flex items-baseline gap-1.5 text-[28px] font-bold leading-none text-ink">
                      <span>{data?.count ?? '—'}</span>
                      {data?.count != null && (
                        <span className="text-sm font-medium text-muted">lần ghi nhận</span>
                      )}
                    </p>
                    <p className="mt-3 text-xs text-muted">
                      Số lần công tơ cập nhật trong kỳ
                    </p>
                  </article>

                  <article className="panel flex flex-col justify-between p-5">
                    <div className="flex items-start justify-between gap-3">
                      <h2 className="text-[13px] font-medium text-muted">
                        Cảnh báo trong phạm vi
                      </h2>
                      <span
                        className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${
                          anomalyCount > 0 ? 'bg-warn-bg text-warn' : 'bg-ok-bg text-ok'
                        }`}
                      >
                        {anomalyCount > 0 ? (
                          <AlertTriangle size={17} aria-hidden="true" />
                        ) : (
                          <CheckCircle2 size={17} aria-hidden="true" />
                        )}
                      </span>
                    </div>
                    <div className="mt-3 flex flex-wrap items-center gap-2.5">
                      <p
                        className={`num text-[28px] font-bold leading-none ${
                          anomalyCount > 0 ? 'text-warn' : 'text-ink'
                        }`}
                      >
                        {data?.anomalies ? anomalyCount : '—'}
                      </p>
                      {data?.anomalies && (
                        <span className={`chip ${anomalyCount > 0 ? 'chip-warn' : 'chip-ok'}`}>
                          {anomalyCount > 0 ? 'Cần kiểm tra' : 'Ổn định'}
                        </span>
                      )}
                    </div>
                    <p className="mt-3 text-xs text-muted">
                      {anomalyCount > 0
                        ? 'Phát hiện tiêu thụ điện vượt ngưỡng'
                        : 'Chưa ghi nhận bất thường nào'}
                    </p>
                  </article>
                </section>
              )}

              {data && data.count === 0 && (
                <div className="panel p-4 text-sm text-ink-2">
                  Chưa có số đo trong thời gian bạn được cấp quyền. Dữ liệu mới sẽ tự cập nhật khi công tơ ghi nhận số đo.
                </div>
              )}

              <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_390px]">
                <div className="min-w-0 space-y-5">
                  {(!!zones.length || (data?.data?.length ?? 0) > 1) && (
                    <section id="portal-zones" className="panel overflow-hidden">
                      <div className="panel-head">
                        <div className="flex items-center gap-2">
                          <MapPin size={16} className="text-shell" aria-hidden="true" />
                          <h2 className="panel-title">Khu vực được phép xem</h2>
                        </div>
                        <span className="chip chip-ok">
                          <span className="h-1.5 w-1.5 rounded-full bg-ok" aria-hidden="true" />
                          Đang theo dõi
                        </span>
                      </div>

                      <div className="space-y-4 p-5">
                        <PortalSparkline points={data?.data || []} formatValue={formatKwh} />

                        {!!zones.length && (
                          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                            {zones.map((zone) => (
                              <article
                                key={zone.id}
                                className="rounded-xl border border-line bg-sunken/50 p-4"
                              >
                                <h3 className="text-sm font-semibold text-ink">{zone.name}</h3>
                                <p className="num mt-2 text-xl font-bold text-shell">
                                  {zone.latest_reading?.meter_reading_kwh != null
                                    ? formatKwh(zone.latest_reading.meter_reading_kwh)
                                    : '—'}{' '}
                                  <span className="text-xs font-medium text-muted">kWh</span>
                                </p>
                                <p className="meta mt-1.5">
                                  {zone.latest_reading?.timestamp
                                    ? new Date(zone.latest_reading.timestamp).toLocaleString('vi-VN')
                                    : 'Chưa có số đo'}
                                </p>
                              </article>
                            ))}
                          </div>
                        )}
                      </div>
                    </section>
                  )}

                  {Boolean(data?.anomalies?.length || data?.data?.length) && (
                    <section id="portal-activity" className="panel overflow-hidden">
                      <div className="panel-head">
                        <div role="tablist" aria-label="Hoạt động tiêu thụ" className="flex flex-wrap items-center gap-2">
                          <button
                            type="button"
                            role="tab"
                            aria-selected={activityTab === 'anomalies'}
                            onClick={() => setActivityTab('anomalies')}
                            className={`flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors ${
                              activityTab === 'anomalies'
                                ? 'bg-shell text-white'
                                : 'bg-sunken text-ink-2 hover:text-ink'
                            }`}
                          >
                            <span>Cảnh báo tiêu thụ bất thường</span>
                            <span
                              className={`num rounded-full px-1.5 py-0.5 text-[10px] font-bold ${
                                activityTab === 'anomalies'
                                  ? 'bg-white/20 text-white'
                                  : 'bg-white text-ink'
                              }`}
                            >
                              {anomalyCount}
                            </span>
                          </button>

                          <button
                            type="button"
                            role="tab"
                            aria-selected={activityTab === 'history'}
                            onClick={() => setActivityTab('history')}
                            className={`flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors ${
                              activityTab === 'history'
                                ? 'bg-shell text-white'
                                : 'bg-sunken text-ink-2 hover:text-ink'
                            }`}
                          >
                            <span>Lịch sử gần nhất</span>
                            <span
                              className={`num rounded-full px-1.5 py-0.5 text-[10px] font-bold ${
                                activityTab === 'history'
                                  ? 'bg-white/20 text-white'
                                  : 'bg-white text-ink'
                              }`}
                            >
                              {recentHistory.length}
                            </span>
                          </button>
                        </div>

                        <span className="meta">Theo dõi thời gian thực</span>
                      </div>

                      {activityTab === 'anomalies' ? (
                        anomalyCount > 0 ? (
                          <div>
                            <div className="divide-y divide-line">
                              {visibleAnomalies.map((anom) => {
                                const sev =
                                  SEVERITY_MAP[String(anom.severity || '').toUpperCase()] ||
                                  SEVERITY_MAP.LOW;
                                return (
                                  <div
                                    key={anom.id}
                                    className="flex flex-wrap items-center justify-between gap-3 px-5 py-3.5 text-sm hover:bg-sunken/50"
                                  >
                                    <div className="flex min-w-0 items-center gap-2.5">
                                      <span className={`chip shrink-0 ${sev.chip}`}>{sev.label}</span>
                                      <span className="truncate font-medium text-ink">
                                        {anom.subsystem || anom.suggested_action || 'Cảnh báo tải cao'}
                                      </span>
                                    </div>
                                    <div className="flex items-center gap-3">
                                      <span className="num text-xs text-muted">
                                        {new Date(anom.timestamp).toLocaleString('vi-VN')}
                                      </span>
                                      <span className="chip chip-crit num">
                                        +{Number(anom.delta_kwh || 0).toFixed(2)} kWh
                                      </span>
                                    </div>
                                  </div>
                                );
                              })}
                            </div>

                            {anomalyCount > 6 && (
                              <div className="border-t border-line px-5 py-3 text-center">
                                <button
                                  type="button"
                                  onClick={() => setShowAllAnomalies((prev) => !prev)}
                                  className="inline-flex items-center gap-1.5 text-xs font-semibold text-shell hover:underline"
                                >
                                  {showAllAnomalies ? (
                                    <>
                                      <span>Thu gọn danh sách</span>
                                      <ChevronUp size={14} aria-hidden="true" />
                                    </>
                                  ) : (
                                    <>
                                      <span>Xem thêm {anomalyCount - 6} cảnh báo khác</span>
                                      <ChevronDown size={14} aria-hidden="true" />
                                    </>
                                  )}
                                </button>
                              </div>
                            )}
                          </div>
                        ) : (
                          <div className="flex items-center gap-3 px-5 py-6 text-sm text-ink-2">
                            <CheckCircle2 size={20} className="shrink-0 text-ok" aria-hidden="true" />
                            <span>Không có cảnh báo tiêu thụ bất thường trong phạm vi đang xem.</span>
                          </div>
                        )
                      ) : recentHistory.length > 0 ? (
                        <div className="max-h-96 overflow-auto">
                          <table className="w-full border-collapse text-left text-sm">
                            <thead className="sticky top-0 border-b border-line bg-sunken text-xs text-muted">
                              <tr>
                                <th scope="col" className="px-5 py-2.5 font-medium">
                                  Thời điểm
                                </th>
                                <th scope="col" className="px-5 py-2.5 text-right font-medium">
                                  Điện năng
                                </th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-line">
                              {recentHistory.map((point) => (
                                <tr key={point.timestamp} className="hover:bg-sunken/60">
                                  <td className="num px-5 py-2.5 text-ink-2">
                                    {new Date(point.timestamp).toLocaleString('vi-VN')}
                                  </td>
                                  <td className="num px-5 py-2.5 text-right font-semibold text-ink">
                                    {formatKwh(point.meter_reading_kwh)} kWh
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      ) : (
                        <p className="px-5 py-6 text-sm text-muted">Chưa có lịch sử số đo.</p>
                      )}
                    </section>
                  )}
                </div>

                <div className="min-w-0 space-y-5">
                  {context && (
                    <section className="panel overflow-hidden">
                      <div className="panel-head">
                        <div className="flex items-center gap-2.5">
                          <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-ok-bg text-ok">
                            <Sparkles size={16} aria-hidden="true" />
                          </span>
                          <div>
                            <h2 className="panel-title">Trợ lý trong phạm vi đang xem</h2>
                            <p className="meta">Hỗ trợ giải đáp số liệu</p>
                          </div>
                        </div>
                        <span className="chip chip-mute">
                          <Lock size={11} aria-hidden="true" />
                          Riêng tư
                        </span>
                      </div>

                      <div className="space-y-4 p-5">
                        <p className="text-xs leading-relaxed text-muted">
                          Sử dụng số liệu đã được cấp quyền. Chưa có dự báo riêng cho từng hộ.
                        </p>

                        {chat.length > 0 && (
                          <div className="max-h-72 space-y-3 overflow-y-auto pr-1 text-sm">
                            {chat.map((turn, index) => (
                              <div key={index} className="space-y-2">
                                <div className="flex justify-end">
                                  <p className="max-w-[88%] rounded-2xl rounded-br-sm bg-shell px-3.5 py-2.5 text-white">
                                    {turn.question}
                                  </p>
                                </div>
                                <div className="rounded-2xl rounded-bl-sm border border-line bg-sunken/70 p-3.5">
                                  <p className="mb-1 text-[11px] font-semibold text-shell">
                                    Trợ lý EcoTrack
                                  </p>
                                  <p className="leading-relaxed text-ink">{turn.answer}</p>
                                </div>
                              </div>
                            ))}
                          </div>
                        )}

                        <div className="flex flex-wrap gap-1.5">
                          {QUICK_QUESTIONS.map((q) => (
                            <button
                              key={q}
                              type="button"
                              disabled={busy}
                              onClick={() => sendQuestion(q)}
                              className="rounded-full border border-line bg-sunken px-2.5 py-1 text-[11px] font-medium text-ink-2 transition-colors hover:border-line-strong hover:text-ink"
                            >
                              {q}
                            </button>
                          ))}
                        </div>

                        <form onSubmit={ask} className="flex gap-2">
                          <input
                            name="message"
                            value={chatInput}
                            onChange={(e) => setChatInput(e.target.value)}
                            aria-label="Câu hỏi"
                            required
                            maxLength={4000}
                            className={field}
                            placeholder="Tổng điện năng của hộ tôi là bao nhiêu?"
                          />
                          <button disabled={busy} className={`${button} shrink-0 px-4`}>
                            <Send size={14} aria-hidden="true" />
                            <span>Gửi</span>
                          </button>
                        </form>
                      </div>
                    </section>
                  )}

                  <InviteForm
                    invite={invite}
                    setInvite={setInvite}
                    busy={busy}
                    onSubmit={acceptInvitation}
                    notice={inviteNotice}
                  />

                  {!!ownerHouseholds.length && <OwnerInvitations households={ownerHouseholds} />}
                </div>
              </div>

              {isManager && (
                <Management
                  key={context.building_id}
                  buildingId={context.building_id}
                  onChanged={reloadIdentity}
                  onScopes={recordManagement}
                />
              )}
            </>
          )}

          {!contexts.length && !!ownerHouseholds.length && (
            <div className="mx-auto max-w-3xl">
              <OwnerInvitations households={ownerHouseholds} />
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

// Decorative: the building the data comes from, drawn as a plan with a few rooms lit.
function FloorPlanArt() {
  const rooms = [
    [20, 20],
    [112, 20],
    [204, 20],
    [296, 20],
    [20, 126],
    [112, 126],
    [204, 126],
    [296, 126],
  ];
  const lit = { 1: '#135056', 2: '#e49b0f', 5: '#135056', 6: '#1c6a70' };
  return (
    <svg viewBox="0 0 388 232" className="hidden max-h-64 w-full max-w-lg lg:block" aria-hidden="true">
      <rect x="6" y="6" width="376" height="220" fill="none" stroke="#9dbdb8" strokeWidth="3" />
      <rect x="12" y="98" width="364" height="30" fill="none" stroke="#2b6469" strokeDasharray="3 5" />
      {rooms.map(([x, y], i) => (
        <rect
          key={i}
          x={x}
          y={y}
          width="84"
          height="80"
          fill={lit[i] || 'none'}
          stroke="#9dbdb8"
          strokeWidth="1.5"
        />
      ))}
    </svg>
  );
}

function InviteForm({ invite, setInvite, busy, onSubmit, notice = '' }) {
  return (
    <section className="panel overflow-hidden">
      <div className="panel-head">
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-ok-bg text-ok">
            <UserPlus size={15} aria-hidden="true" />
          </span>
          <h2 className="panel-title">Tham gia hộ gia đình bằng lời mời</h2>
        </div>
      </div>

      {!!notice && (
        <p role="status" className="border-b border-line bg-ok-bg/40 px-5 py-3 text-xs text-ok">
          {notice}
        </p>
      )}

      <form onSubmit={onSubmit} className="space-y-3 p-5">
        <p className="text-xs leading-relaxed text-muted">
          Nhập mã mời được cấp từ chủ hộ hoặc ban quản lý tòa nhà để mở rộng phạm vi xem dữ liệu căn hộ.
        </p>
        <label className="block">
          <span className="sr-only">Mã mời</span>
          <input
            value={invite}
            onChange={(event) => setInvite(event.target.value)}
            placeholder="Dán mã mời được gửi cho email của bạn"
            required
            minLength={64}
            maxLength={64}
            className={field}
            autoComplete="off"
          />
        </label>
        <button disabled={busy} className={`${button} w-full py-2.5`}>
          <span>Nhận lời mời</span>
          <ArrowRight size={15} aria-hidden="true" />
        </button>
      </form>
    </section>
  );
}

const roleLabel = (role) => (role === 'OWNER' ? 'Chủ hộ' : 'Thành viên');

// NULL email_sent_at means the invitation exists but nothing was delivered.
function deliveryLabel(invitation) {
  if (invitation.email_sent_at) {
    return `đã gửi email ${new Date(invitation.email_sent_at).toLocaleString('vi-VN')}`;
  }
  return invitation.email_attempts
    ? 'chưa gửi được email, hãy chuyển mã mời thủ công'
    : 'chưa gửi email';
}

// Mail delivery is best effort: when it fails the operator still has the code.
function inviteResult(data) {
  return data.email_sent
    ? `Đã gửi email lời mời tới ${data.email} (hiệu lực 48 giờ).${data.superseded ? ' Mã mời trước đó đã bị vô hiệu.' : ''}`
    : `${data.email_error === 'smtp_not_configured' ? 'Chưa cấu hình gửi email' : 'Gửi email thất bại'}.` +
        ` Hãy chuyển mã mời này cho ${data.email} (hiệu lực 48 giờ): ${data.token}`;
}

function OwnerInvitations({ households }) {
  const [result, setResult] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setResult('');
    try {
      const body = Object.fromEntries(new FormData(event.currentTarget));
      const response = await accountApi.post('/api/v1/portal/invitations', body);
      setResult(inviteResult(response.data));
    } catch (error) {
      setResult(message(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel overflow-hidden">
      <div className="panel-head">
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-sunken text-shell">
            <Users size={15} aria-hidden="true" />
          </span>
          <h2 className="panel-title">Mời thành viên vào hộ của bạn</h2>
        </div>
      </div>

      <form onSubmit={submit} className="space-y-3 p-5">
        <select aria-label="Hộ gia đình nhận thành viên" name="household_id" className={field}>
          {households.map((household) => (
            <option key={household.id} value={household.id}>
              {household.name}
            </option>
          ))}
        </select>
        <input
          className={field}
          aria-label="Email thành viên"
          type="email"
          name="email"
          required
          placeholder="Email người được mời"
        />
        <button className={`${button} w-full py-2.5`} disabled={busy}>
          Tạo mã mời thành viên
        </button>
        {result && (
          <p role="status" className="num break-all text-xs text-ok">
            {result}
          </p>
        )}
      </form>
    </section>
  );
}

function Management({ buildingId, onChanged, onScopes }) {
  const [state, setState] = useState(null);
  const [result, setResult] = useState('');
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const response = await accountApi.get('/api/v1/portal/manage', {
      params: { building_id: buildingId },
    });
    setState(response.data);
    onScopes(buildingId, response.data.units);
  }, [buildingId, onScopes]);

  useEffect(() => {
    refresh().catch((error) => setResult(message(error)));
  }, [refresh]);

  async function mutate(url, body) {
    setBusy(true);
    setResult('');
    try {
      const response = await accountApi.post(`/api/v1/portal/${url}`, body);
      setResult(response.data.token ? inviteResult(response.data) : 'Đã lưu.');
      await refresh();
      await onChanged();
    } catch (error) {
      setResult(message(error));
    } finally {
      setBusy(false);
    }
  }

  const households =
    state?.units.flatMap((unit) =>
      unit.households
        .filter((household) => !household.ends_at)
        .map((household) => ({ ...household, code: unit.code }))
    ) || [];
  const unassigned = state?.unassigned_zones.filter((zone) => zone.meter?.scope === 'UNASSIGNED') || [];

  return (
    <section id="portal-management" className="panel overflow-hidden">
      <div className="panel-head">
        <div>
          <h2 className="panel-title">Quản lý căn hộ và cư dân</h2>
          <p className="meta mt-0.5">
            Gán công tơ cho từng căn hộ. Khu vực chưa gán sẽ không hiển thị cho cư dân.
          </p>
        </div>
      </div>

      <div className="grid gap-5 p-5 lg:grid-cols-2">
        <div className="space-y-6">
          <form
            className="grid gap-3 rounded-xl border border-line bg-sunken/40 p-4 sm:grid-cols-2"
            onSubmit={(event) => {
              event.preventDefault();
              const values = Object.fromEntries(new FormData(event.currentTarget));
              mutate('units', {
                ...values,
                building_id: buildingId,
                floor: Number(values.floor),
                zone_id: values.zone_id || undefined,
              });
            }}
          >
            <label>
              <span className="field-label">Mã căn hộ</span>
              <input name="code" required maxLength={30} placeholder="101" className={field} />
            </label>
            <label>
              <span className="field-label">Tên hộ gia đình</span>
              <input name="household_name" required maxLength={100} className={field} />
            </label>
            <label>
              <span className="field-label">Tầng</span>
              <input name="floor" type="number" defaultValue={1} min={-10} max={300} required className={field} />
            </label>
            <label>
              <span className="field-label">Công tơ khu vực tương ứng</span>
              <select name="zone_id" className={field}>
                <option value="">Chưa gán công tơ</option>
                {unassigned.map((zone) => (
                  <option key={zone.id} value={zone.id}>
                    {zone.name}
                  </option>
                ))}
              </select>
            </label>
            <div className="sm:col-span-2">
              <button disabled={busy} className={button}>
                Tạo căn hộ và hộ cư trú
              </button>
            </div>
          </form>

          <form
            className="grid gap-3 rounded-xl border border-line bg-sunken/40 p-4 sm:grid-cols-2"
            onSubmit={(event) => {
              event.preventDefault();
              mutate('invitations', Object.fromEntries(new FormData(event.currentTarget)));
            }}
          >
            <select aria-label="Hộ được mời" name="household_id" required className={field}>
              {households.map((household) => (
                <option key={household.id} value={household.id}>
                  Căn {household.code} — {household.name}
                </option>
              ))}
            </select>
            <select aria-label="Vai trò" name="role" className={field}>
              <option value="OWNER">Chủ hộ</option>
              <option value="MEMBER">Thành viên</option>
            </select>
            <input
              aria-label="Email cư dân"
              type="email"
              name="email"
              required
              placeholder="Email cư dân được mời"
              className={`${field} sm:col-span-2`}
            />
            <div className="sm:col-span-2">
              <button disabled={busy || !households.length} className={button}>
                Tạo mã mời cư dân
              </button>
            </div>
          </form>

          {unassigned.length > 0 && (
            <div className="space-y-2 rounded-xl border border-line p-4">
              <p className="text-xs font-semibold text-muted">Khu vực chưa gán căn hộ</p>
              {unassigned.map((zone) => (
                <div
                  key={zone.id}
                  className="flex flex-wrap items-center justify-between gap-2 border-t border-line pt-2.5 text-sm first:border-t-0 first:pt-0"
                >
                  <span className="text-ink-2">{zone.name}</span>
                  <button
                    disabled={busy}
                    className="btn btn-quiet btn-sm"
                    onClick={() =>
                      mutate('common-zones', { building_id: buildingId, zone_id: zone.id })
                    }
                  >
                    Công bố là khu vực chung
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="space-y-4">
          {state?.units.map((unit) => (
            <article key={unit.id} className="space-y-3 rounded-xl border border-line bg-sunken/30 p-4">
              <h3 className="text-sm font-bold text-ink">Căn {unit.code}</h3>
              {!!unassigned.length && (
                <form
                  className="flex gap-2"
                  onSubmit={(event) => {
                    event.preventDefault();
                    mutate(`units/${unit.id}/zones`, {
                      zone_id: new FormData(event.currentTarget).get('zone_id'),
                    });
                  }}
                >
                  <select
                    name="zone_id"
                    aria-label={`Công tơ căn ${unit.code}`}
                    className={field}
                    required
                  >
                    {unassigned.map((zone) => (
                      <option key={zone.id} value={zone.id}>
                        {zone.name}
                      </option>
                    ))}
                  </select>
                  <button className="btn btn-quiet shrink-0" disabled={busy}>
                    Gán thêm công tơ
                  </button>
                </form>
              )}

              {unit.households
                .filter((household) => !household.ends_at)
                .map((household) => (
                  <div key={household.id} className="space-y-2">
                    <p className="text-sm font-semibold text-ink-2">{household.name}</p>
                    {household.members
                      .filter((member) => !member.ends_at)
                      .map((member) => (
                        <div
                          key={member.id}
                          className="flex flex-wrap items-center justify-between gap-2 border-t border-line pt-2 text-sm"
                        >
                          <span className="min-w-0 break-words text-ink-2">
                            {member.user.name} · {member.user.email} · {roleLabel(member.role)}
                          </span>
                          <button
                            className="btn btn-quiet btn-sm"
                            disabled={busy}
                            onClick={() => mutate(`members/${member.id}/revoke`, {})}
                          >
                            Thu hồi quyền
                          </button>
                        </div>
                      ))}

                    {!!household.invitations?.length && (
                      <ul className="space-y-1 border-t border-line pt-2">
                        {household.invitations.map((invitation) => (
                          <li
                            key={invitation.id}
                            className="flex flex-wrap items-center justify-between gap-2 text-xs"
                          >
                            <span className="min-w-0 break-words text-ink-2">
                              Lời mời {invitation.email} · {roleLabel(invitation.role)} · {deliveryLabel(invitation)}
                            </span>
                            {/* Resending issues a new code and voids this one. */}
                            <button
                              className="btn btn-quiet btn-sm"
                              disabled={busy}
                              onClick={() =>
                                mutate('invitations', {
                                  household_id: household.id,
                                  email: invitation.email,
                                  role: invitation.role,
                                })
                              }
                            >
                              Gửi lại email
                            </button>
                          </li>
                        ))}
                      </ul>
                    )}

                    <button
                      className="link text-sm !text-warn"
                      disabled={busy}
                      onClick={() => mutate(`households/${household.id}/end`, {})}
                    >
                      Kết thúc kỳ cư trú của hộ này
                    </button>
                  </div>
                ))}

              {!unit.households.some((household) => !household.ends_at) && (
                <form
                  className="flex gap-2"
                  onSubmit={(event) => {
                    event.preventDefault();
                    mutate('households', {
                      unit_id: unit.id,
                      name: new FormData(event.currentTarget).get('name'),
                    });
                  }}
                >
                  <input
                    name="name"
                    aria-label={`Hộ mới căn ${unit.code}`}
                    required
                    maxLength={100}
                    placeholder="Tên hộ cư trú mới"
                    className={field}
                  />
                  <button disabled={busy} className="btn btn-quiet shrink-0">
                    Tạo kỳ cư trú mới
                  </button>
                </form>
              )}
            </article>
          ))}
        </div>
      </div>

      {result && (
        <p role="status" className="num break-all border-t border-line px-5 py-3 text-xs text-ok">
          {result}
        </p>
      )}
    </section>
  );
}

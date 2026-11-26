import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import AccountPortal from '../AccountPortal';
import { accountApi } from '../services/api';

vi.mock('../services/api', () => ({ API_BASE_URL: 'http://localhost:5000', accountApi: { get: vi.fn(), post: vi.fn() } }));
vi.mock('../App', () => ({ default: () => <div>Original system dashboard</div> }));
const building = { id: 'office_tower_01', name: 'Demo Tower' };
const household = { id: '11111111-1111-4111-8111-111111111111', name: 'My household', role: 'MEMBER',
  unit: { code: '101', building_id: building.id, building } };
const resident = { id: 'u1', name: 'Alice', email: 'alice@example.test', staff: [], households: [household], is_platform_admin: false };
const signedOut = { response: { status: 401 } };
let currentUser;
let manageUnits;
class Source {
  static instances = [];
  constructor(url, options) { this.url = url; this.options = options; Source.instances.push(this); }
  addEventListener() {}
  close() { this.closed = true; }
}
beforeEach(() => {
  vi.resetAllMocks(); currentUser = null; manageUnits = []; Source.instances = []; vi.stubGlobal('EventSource', Source);
  window.history.replaceState({}, '', '/');
  accountApi.get.mockImplementation(async (path, options) => {
    if (path === '/api/v1/auth/me') {
      if (!currentUser) throw signedOut;
      return { data: { user: currentUser } };
    }
    if (path === '/api/v1/portal/buildings') return { data: { buildings: currentUser?.households.length || currentUser?.staff.length ? [building] : [] } };
    if (path === '/api/v1/portal/manage') return { data: { units: manageUnits, unassigned_zones: [] } };
    if (path === '/api/v1/portal/zones') return { data: { zones: [] } };
    if (path === '/api/v1/portal/overview') return { data: { count: 1, data: [], anomalies: [],
      metrics: { total_consumption_kwh: options.params.scope === 'household' ? 10 : 100 } } };
    throw new Error(`Unexpected path ${path}`);
  });
});
afterEach(() => vi.unstubAllGlobals());

describe('Resident account portal', () => {
  it('requires sign-in before requesting any household data', async () => {
    render(<AccountPortal />);
    expect(await screen.findByRole('heading', { name: 'Đăng nhập' })).toBeInTheDocument();
    expect(accountApi.get).toHaveBeenCalledTimes(1);
    expect(Source.instances).toHaveLength(0);
    expect(screen.getByRole('link', { name: 'Tiếp tục bằng Google' })).toHaveAttribute('href', 'http://localhost:5000/api/v1/auth/google/start');
  });
  it('explains when Google requires linking an existing password account', async () => {
    window.history.replaceState({}, '', '/?auth_error=google_link_required');
    render(<AccountPortal />);
    expect(await screen.findByText(/Email này đã có tài khoản/)).toBeInTheDocument();
    await screen.findByRole('heading', { name: 'Đăng nhập' });
    expect(screen.getByRole('alert')).toHaveTextContent('Liên kết Google');
    expect(window.location.search).toBe('');
  });
  it('keeps a Google linking failure visible after the signed-in dashboard loads', async () => {
    currentUser = resident;
    window.history.replaceState({}, '', '/?auth_error=google_failed');
    render(<AccountPortal />);
    await screen.findByText('10.00 kWh');
    expect(screen.getByRole('alert')).toHaveTextContent('Đăng nhập Google chưa thành công');
    expect(screen.getByRole('link', { name: 'Liên kết Google' })).toBeInTheDocument();
  });

  it('registers an account without granting a household automatically', async () => {
    accountApi.post.mockImplementation(async () => { currentUser = { ...resident, households: [] }; return { data: {} }; });
    render(<AccountPortal />);
    fireEvent.click(await screen.findByText('Chưa có tài khoản? Đăng ký'));
    fireEvent.change(screen.getByLabelText('Họ tên'), { target: { value: 'Alice' } });
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'alice@example.test' } });
    fireEvent.change(screen.getByLabelText('Mật khẩu'), { target: { value: 'LongPassword123' } });
    fireEvent.click(screen.getByRole('button', { name: 'Đăng ký' }));
    expect(await screen.findByText(/Tài khoản chưa thuộc hộ gia đình nào/)).toBeInTheDocument();
    expect(accountApi.post).toHaveBeenCalledWith('/api/v1/auth/register', {
      name: 'Alice', email: 'alice@example.test', password: 'LongPassword123',
    });
    expect(screen.queryByLabelText('Phạm vi xem dữ liệu')).not.toBeInTheDocument();
  });

  it('shows own household and shared views, and sends credentials on SSE', async () => {
    currentUser = resident;
    render(<AccountPortal />);
    expect(await screen.findByText('10.00 kWh')).toBeInTheDocument();
    const options = [...screen.getByLabelText('Phạm vi xem dữ liệu').options];
    expect(options).toHaveLength(3);
    expect(options[0].text).toContain('Căn 101');
    expect(Source.instances[0].options).toEqual({ withCredentials: true });
    expect(Source.instances[0].url).toContain(`household_id=${household.id}`);
    fireEvent.change(screen.getByLabelText('Phạm vi xem dữ liệu'), { target: { value: `building:${building.id}` } });
    expect(await screen.findByText('100.00 kWh')).toBeInTheDocument();
    expect(Source.instances[0].closed).toBe(true);
    expect(accountApi.get).toHaveBeenCalledWith('/api/v1/portal/overview', { params: { building_id: building.id, scope: 'building' } });
    expect(screen.queryByRole('button', { name: 'Dashboard hệ thống' })).not.toBeInTheDocument();
  });
  it('allows an operator role to open and return from the original dashboard', async () => {
    currentUser = { ...resident, households: [], is_platform_admin: true, role: 'ADMIN' };
    render(<AccountPortal />);
    fireEvent.click(await screen.findByRole('button', { name: 'Dashboard hệ thống' }));
    expect(await screen.findByText('Original system dashboard')).toBeInTheDocument();
    expect(window.location.pathname).toBe('/dashboard');
    fireEvent.click(screen.getByRole('button', { name: 'Về cổng cư dân' }));
    expect(await screen.findByRole('button', { name: 'Dashboard hệ thống' })).toBeInTheDocument();
    expect(window.location.pathname).toBe('/');
    expect(screen.queryByText('Original system dashboard')).not.toBeInTheDocument();
  });

  it('opens a bookmarked dashboard URL and follows browser navigation', async () => {
    currentUser = { ...resident, households: [], is_platform_admin: true, role: 'ADMIN' };
    window.history.replaceState({}, '', '/dashboard');
    render(<AccountPortal />);
    expect(await screen.findByText('Original system dashboard')).toBeInTheDocument();

    window.history.pushState({}, '', '/');
    fireEvent(window, new PopStateEvent('popstate'));
    expect(await screen.findByRole('button', { name: 'Dashboard hệ thống' })).toBeInTheDocument();
  });

  it('lets building staff (TECHNICIAN) open the operations dashboard', async () => {
    currentUser = { ...resident, households: [], role: 'TECHNICIAN', staff: [{ building_id: building.id, role: 'TECHNICIAN' }] };
    render(<AccountPortal />);
    fireEvent.click(await screen.findByRole('button', { name: 'Dashboard hệ thống' }));
    expect(await screen.findByText('Original system dashboard')).toBeInTheDocument();
  });

  it('accepts an invitation then refreshes household membership', async () => {
    currentUser = { ...resident, households: [] };
    accountApi.post.mockImplementation(async () => { currentUser = resident; return { data: {} }; });
    render(<AccountPortal />);
    const input = await screen.findByPlaceholderText('Dán mã mời được gửi cho email của bạn');
    fireEvent.change(input, { target: { value: 'a'.repeat(64) } });
    fireEvent.click(screen.getByRole('button', { name: 'Nhận lời mời' }));
    expect(await screen.findByText('10.00 kWh')).toBeInTheDocument();
    expect(accountApi.post).toHaveBeenCalledWith('/api/v1/portal/invitations/accept', { token: 'a'.repeat(64) });
  });

  it('prefills the invitation code from the email link and strips it from the URL', async () => {
    currentUser = { ...resident, households: [] };
    const token = 'b'.repeat(64);
    window.history.replaceState({}, '', `/?invite_token=${token}`);
    render(<AccountPortal />);
    const input = await screen.findByPlaceholderText('Dán mã mời được gửi cho email của bạn');
    expect(input).toHaveValue(token);
    expect(screen.getByText(/Đã nhận liên kết lời mời/)).toBeInTheDocument();
    expect(window.location.search).toBe('');
    // Opening the link must not join the household on its own.
    expect(accountApi.post).not.toHaveBeenCalled();
  });

  it('confirms that an owner invitation was emailed to the invitee', async () => {
    currentUser = { ...resident, households: [{ ...household, role: 'OWNER' }] };
    accountApi.post.mockResolvedValue({ data: { token: 'c'.repeat(64), email: 'bob@example.test', email_sent: true } });
    render(<AccountPortal />);
    fireEvent.change(await screen.findByLabelText('Email thành viên'), { target: { value: 'bob@example.test' } });
    fireEvent.click(screen.getByRole('button', { name: 'Tạo mã mời thành viên' }));
    expect(await screen.findByText('Đã gửi email lời mời tới bob@example.test (hiệu lực 48 giờ).')).toBeInTheDocument();
    expect(accountApi.post).toHaveBeenCalledWith('/api/v1/portal/invitations',
      { household_id: household.id, email: 'bob@example.test' });
  });

  it('falls back to the code when the invitation email cannot be sent', async () => {
    currentUser = { ...resident, households: [{ ...household, role: 'OWNER' }] };
    accountApi.post.mockResolvedValue({ data: { token: 'd'.repeat(64), email: 'bob@example.test',
      email_sent: false, email_error: 'smtp_not_configured' } });
    render(<AccountPortal />);
    fireEvent.change(await screen.findByLabelText('Email thành viên'), { target: { value: 'bob@example.test' } });
    fireEvent.click(screen.getByRole('button', { name: 'Tạo mã mời thành viên' }));
    expect(await screen.findByText(/Chưa cấu hình gửi email/)).toHaveTextContent('d'.repeat(64));
  });

  it('clears private data on logout', async () => {
    currentUser = resident; accountApi.post.mockResolvedValue({ data: {} });
    render(<AccountPortal />);
    await screen.findByText('10.00 kWh');
    fireEvent.click(screen.getByRole('button', { name: 'Đăng xuất' }));
    await waitFor(() => expect(screen.queryByText('10.00 kWh')).not.toBeInTheDocument());
    expect(screen.getByRole('heading', { name: 'Đăng nhập' })).toBeInTheDocument();
  });
  it('lets an authorized manager provision an apartment without auto-assigning a room', async () => {
    currentUser = { ...resident, households: [], staff: [{ building_id: building.id, role: 'MANAGER' }] };
    accountApi.post.mockResolvedValue({ data: {} });
    render(<AccountPortal />);
    await screen.findByText('Quản lý căn hộ và cư dân');
    fireEvent.change(screen.getByLabelText('Mã căn hộ'), { target: { value: '103' } });
    fireEvent.change(screen.getByLabelText('Tên hộ gia đình'), { target: { value: 'New household' } });
    fireEvent.click(screen.getByRole('button', { name: 'Tạo căn hộ và hộ cư trú' }));
    await waitFor(() => expect(accountApi.post).toHaveBeenCalledWith('/api/v1/portal/units', {
      building_id: building.id, code: '103', floor: 1, household_name: 'New household', zone_id: undefined,
    }));
    expect(await screen.findByText('Đã lưu.')).toBeInTheDocument();
  });

  it('shows the delivery state of outstanding invitations and resends one', async () => {
    currentUser = { ...resident, households: [], staff: [{ building_id: building.id, role: 'MANAGER' }] };
    manageUnits = [{ id: 'unit-1', code: '101', households: [{ id: household.id, name: 'My household',
      ends_at: null, members: [], invitations: [
        { id: 'inv-1', email: 'sent@example.test', role: 'MEMBER', expires_at: '2026-11-05T03:00:00.000Z',
          email_sent_at: '2026-11-03T03:00:00.000Z', email_attempts: 1, email_last_error: null },
        { id: 'inv-2', email: 'failed@example.test', role: 'OWNER', expires_at: '2026-11-05T03:00:00.000Z',
          email_sent_at: null, email_attempts: 2, email_last_error: 'send_failed: mailbox unavailable' },
      ] }], zones: [] }];
    accountApi.post.mockResolvedValue({ data: { token: 'e'.repeat(64), email: 'failed@example.test',
      email_sent: true, superseded: 1 } });
    render(<AccountPortal />);
    expect(await screen.findByText(/Lời mời sent@example.test · Thành viên · đã gửi email/)).toBeInTheDocument();
    expect(screen.getByText(/Lời mời failed@example.test · Chủ hộ · chưa gửi được email/)).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole('button', { name: 'Gửi lại email' })[1]);
    await waitFor(() => expect(accountApi.post).toHaveBeenCalledWith('/api/v1/portal/invitations',
      { household_id: household.id, email: 'failed@example.test', role: 'OWNER' }));
    expect(await screen.findByText(/Mã mời trước đó đã bị vô hiệu/)).toBeInTheDocument();
  });
});

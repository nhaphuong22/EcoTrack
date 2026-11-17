import { describe, it, expect, vi, beforeEach, afterAll } from 'vitest';
import request from 'supertest';
import express from 'express';

const sendMail = vi.fn();

const mock = { household: { findUnique: vi.fn() },
  invitation: { create: vi.fn(), update: vi.fn(), updateMany: vi.fn() },
  $transaction: vi.fn() };
global.__mockPrisma = mock;

const portalRouter = require('../src/routes/portal');
const errorHandler = require('../src/middleware/errorHandler');
const { invitationTemplate, useTransport, resetTransport } = require('../src/services/mailService');

const manager = { id: '00000000-0000-4000-8000-000000000001', name: 'Quản lý Toà A',
  email: 'manager@example.test', is_platform_admin: false, memberships: [],
  staff: [{ building_id: 'BLD-A', role: 'MANAGER' }] };
const app = express();
app.use(express.json());
app.use('/api/v1/portal', (req, res, next) => { req.user = manager; next(); }, portalRouter);
app.use(errorHandler);

const HOUSEHOLD = '00000000-0000-4000-8000-0000000000aa';
const keys = ['SMTP_HOST', 'SMTP_PORT', 'SMTP_FROM', 'SMTP_USER', 'SMTP_PASSWORD', 'APP_FRONTEND_URL'];
const previous = Object.fromEntries(keys.map((key) => [key, process.env[key]]));
let warn;
let error;

beforeEach(() => {
  vi.resetAllMocks(); resetTransport(); useTransport({ sendMail });
  warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
  error = vi.spyOn(console, 'error').mockImplementation(() => {});
  Object.assign(process.env, { SMTP_HOST: 'smtp.example.test', SMTP_PORT: '587',
    SMTP_FROM: 'EcoTrack <no-reply@example.test>', SMTP_USER: 'no-reply@example.test',
    SMTP_PASSWORD: 'secret', APP_FRONTEND_URL: 'http://localhost:3000' });
  mock.household.findUnique.mockResolvedValue({ id: HOUSEHOLD, name: 'Hộ Nguyễn', ends_at: null,
    unit: { id: 'unit-1', code: '101', building_id: 'BLD-A', building: { id: 'BLD-A', name: 'Toà A' } } });
  mock.invitation.create.mockImplementation(async ({ data }) => ({ ...data, id: 'invitation-1' }));
  mock.invitation.updateMany.mockResolvedValue({ count: 0 });
  mock.invitation.update.mockImplementation(async ({ data }) => data);
  mock.$transaction.mockImplementation(async (run) => run(mock));
});
const delivery = () => mock.invitation.update.mock.calls[0][0];
afterAll(() => { for (const key of keys) previous[key] === undefined ? delete process.env[key] : process.env[key] = previous[key]; });

const invite = (body = {}) => request(app).post('/api/v1/portal/invitations')
  .send({ household_id: HOUSEHOLD, email: 'Resident@Example.test', role: 'OWNER', ...body });

describe('Gửi email khi quản lý mời vào hộ gia đình', () => {
  it('gửi lời mời tới đúng email, kèm liên kết chứa mã mời', async () => {
    sendMail.mockResolvedValue({ messageId: 'queued' });
    const response = await invite();
    expect(response.status).toBe(201);
    expect(response.body.email_sent).toBe(true);
    expect(response.body.email).toBe('resident@example.test');
    expect(sendMail).toHaveBeenCalledTimes(1);
    const mail = sendMail.mock.calls[0][0];
    expect(mail.to).toBe('resident@example.test');
    expect(mail.from).toBe('EcoTrack <no-reply@example.test>');
    expect(mail.subject).toContain('Hộ Nguyễn');
    // The link and the pasteable code both carry the plaintext token, while the
    // database only ever stores its hash.
    expect(mail.html).toContain(`invite_token=${response.body.token}`);
    expect(mail.text).toContain(response.body.token);
    expect(mail.html).toContain('Căn 101');
    expect(mock.invitation.create.mock.calls[0][0].data.token_hash).not.toBe(response.body.token);
  });

  it('ghi lại thời điểm gửi thành công và tăng số lần thử', async () => {
    sendMail.mockResolvedValue({ messageId: 'queued' });
    await invite();
    expect(mock.invitation.update).toHaveBeenCalledTimes(1);
    expect(delivery().where).toEqual({ id: 'invitation-1' });
    expect(delivery().data.email_sent_at).toBeInstanceOf(Date);
    expect(delivery().data.email_attempts).toEqual({ increment: 1 });
    expect(delivery().data.email_last_error).toBeNull();
  });

  it('vô hiệu lời mời cũ chưa dùng của cùng email trong cùng hộ', async () => {
    sendMail.mockResolvedValue({ messageId: 'queued' });
    mock.invitation.updateMany.mockResolvedValue({ count: 1 });
    const response = await invite();
    expect(response.body.superseded).toBe(1);
    const [{ where, data }] = mock.invitation.updateMany.mock.calls[0];
    expect(where).toMatchObject({ household_id: HOUSEHOLD, email: 'resident@example.test', accepted_at: null });
    expect(where.expires_at.gt).toBeInstanceOf(Date);
    // The superseding runs in the same transaction as the new invitation.
    expect(data.expires_at).toBeInstanceOf(Date);
    expect(mock.$transaction).toHaveBeenCalledTimes(1);
  });

  it('vẫn tạo lời mời và trả mã khi chưa cấu hình SMTP', async () => {
    delete process.env.SMTP_HOST;
    const response = await invite();
    expect(response.status).toBe(201);
    expect(response.body).toMatchObject({ email_sent: false, email_error: 'smtp_not_configured' });
    expect(response.body.token).toMatch(/^[a-f0-9]{64}$/);
    expect(sendMail).not.toHaveBeenCalled();
    expect(warn).toHaveBeenCalled();
    expect(delivery().data.email_sent_at).toBeUndefined();
    expect(delivery().data.email_last_error).toContain('smtp_not_configured');
  });

  it('không hủy lời mời khi máy chủ mail lỗi', async () => {
    sendMail.mockRejectedValue(new Error('mailbox unavailable'));
    const response = await invite();
    expect(response.status).toBe(201);
    expect(response.body).toMatchObject({ email_sent: false, email_error: 'send_failed' });
    expect(mock.invitation.create).toHaveBeenCalledTimes(1);
    expect(error).toHaveBeenCalled();
    // The failure is kept on the row, bounded to the column width.
    expect(delivery().data.email_last_error).toBe('send_failed: mailbox unavailable');
    expect(delivery().data.email_sent_at).toBeUndefined();
  });

  it('không gửi email khi người gọi không có quyền với hộ đó', async () => {
    mock.household.findUnique.mockResolvedValue({ id: HOUSEHOLD, name: 'Hộ khác', ends_at: null,
      unit: { code: '202', building_id: 'BLD-B', building: { id: 'BLD-B', name: 'Toà B' } } });
    const response = await invite();
    expect(response.status).toBe(403);
    expect(sendMail).not.toHaveBeenCalled();
    expect(mock.invitation.create).not.toHaveBeenCalled();
    expect(mock.invitation.updateMany).not.toHaveBeenCalled();
  });

  it('vẫn trả 201 khi không ghi được trạng thái gửi', async () => {
    sendMail.mockResolvedValue({ messageId: 'queued' });
    mock.invitation.update.mockRejectedValue(new Error('column is missing'));
    const response = await invite();
    expect(response.status).toBe(201);
    expect(response.body.email_sent).toBe(true);
    expect(error).toHaveBeenCalled();
  });

  it('nội dung email thoát ký tự HTML và nêu thời hạn theo giờ Việt Nam', () => {
    const content = invitationTemplate({ householdName: 'Hộ <script>alert(1)</script>', unitCode: '101',
      buildingName: 'Toà A', inviterName: 'Quản lý', role: 'MEMBER', token: 'a'.repeat(64),
      expiresAt: new Date('2026-11-05T03:00:00.000Z') });
    expect(content.html).not.toContain('<script>');
    expect(content.html).toContain('&lt;script&gt;');
    expect(content.html).toContain('10:00');
    expect(content.link).toBe(`http://localhost:3000/?invite_token=${'a'.repeat(64)}`);
  });
});

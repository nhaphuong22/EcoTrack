const nodemailer = require('nodemailer');

// Outbound email is optional infrastructure. Without SMTP settings the portal
// keeps working: the invitation token is still returned so an operator can
// share it by hand, and the API reports email_sent=false.
const truthy = (value) => ['1', 'true', 'yes', 'on'].includes(String(value || '').trim().toLowerCase());
const isConfigured = () => Boolean(process.env.SMTP_HOST && process.env.SMTP_FROM);

let cached = null;
let injected = null;
// Lets a caller supply its own transporter (a captured transport in tests, or a
// provider SDK later) in place of the SMTP one built from the environment.
function useTransport(transporter) { injected = transporter; cached = null; }
function transport() {
  if (injected) return injected;
  if (cached) return cached;
  const port = Number(process.env.SMTP_PORT || 587);
  cached = nodemailer.createTransport({
    host: process.env.SMTP_HOST,
    port,
    // Port 465 speaks TLS from the first byte; 587 upgrades with STARTTLS.
    secure: process.env.SMTP_SECURE ? truthy(process.env.SMTP_SECURE) : port === 465,
    auth: process.env.SMTP_USER ? { user: process.env.SMTP_USER, pass: process.env.SMTP_PASSWORD || '' } : undefined,
    connectionTimeout: 10000,
    greetingTimeout: 10000,
    socketTimeout: 15000,
  });
  return cached;
}
// Tests and a transport swap after a config change both need this.
function resetTransport() { cached = null; injected = null; }

const escape = (value) => String(value ?? '').replace(/[&<>"']/g,
  (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character]));

function inviteUrl(token) {
  const base = (process.env.APP_FRONTEND_URL || 'http://localhost:3000').split(',')[0].trim();
  const url = new URL(base);
  url.searchParams.set('invite_token', token);
  return url.toString();
}
const formatDeadline = (expiresAt) => new Intl.DateTimeFormat('vi-VN', {
  dateStyle: 'short', timeStyle: 'short', timeZone: process.env.APP_TIMEZONE || 'Asia/Ho_Chi_Minh',
}).format(expiresAt instanceof Date ? expiresAt : new Date(expiresAt));

function invitationTemplate({ householdName, unitCode, buildingName, inviterName, role, token, expiresAt }) {
  const link = inviteUrl(token);
  const deadline = formatDeadline(expiresAt);
  const roleLabel = role === 'OWNER' ? 'Chủ hộ' : 'Thành viên';
  const place = [unitCode && `Căn ${unitCode}`, buildingName].filter(Boolean).join(' · ');
  const subject = `[EcoTrack] Lời mời tham gia hộ gia đình ${householdName}`;
  const text = [
    'Xin chào,',
    '',
    `${inviterName} đã mời bạn tham gia hộ gia đình "${householdName}"${place ? ` (${place})` : ''} trên EcoTrack với vai trò ${roleLabel}.`,
    '',
    `Nhấn vào liên kết sau để nhận lời mời: ${link}`,
    '',
    `Hoặc đăng nhập EcoTrack và dán mã mời này: ${token}`,
    '',
    `Lời mời có hiệu lực đến ${deadline} và chỉ dùng được cho chính email này.`,
    'Nếu bạn không mong đợi email này, vui lòng bỏ qua.',
    '',
    'EcoTrack — Hệ thống quản trị năng lượng tòa nhà thông minh',
  ].join('\n');
  const html = `<!doctype html><html lang="vi"><body style="margin:0;background:#f4f6f5;padding:24px;font-family:Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#16211d">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#ffffff;border:1px solid #dfe5e2;border-radius:12px">
      <tr><td style="padding:24px 28px 8px">
        <p style="margin:0;font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:#2f7a5a">EcoTrack</p>
        <h1 style="margin:8px 0 0;font-size:20px;line-height:1.35">Lời mời tham gia hộ gia đình ${escape(householdName)}</h1>
      </td></tr>
      <tr><td style="padding:8px 28px 0;font-size:15px;line-height:1.6">
        <p style="margin:0 0 12px"><strong>${escape(inviterName)}</strong> đã mời bạn tham gia hộ gia đình
        <strong>${escape(householdName)}</strong>${place ? ` (${escape(place)})` : ''} với vai trò <strong>${escape(roleLabel)}</strong>.</p>
        <p style="margin:0 0 20px">Sau khi nhận lời mời, bạn có thể xem dữ liệu tiêu thụ điện của hộ mình kể từ thời điểm tham gia.</p>
        <p style="margin:0 0 20px"><a href="${escape(link)}" style="display:inline-block;background:#2f7a5a;color:#ffffff;text-decoration:none;padding:12px 22px;border-radius:8px;font-weight:600">Nhận lời mời</a></p>
        <p style="margin:0 0 6px;font-size:13px;color:#4c5a55">Hoặc đăng nhập EcoTrack rồi dán mã mời:</p>
        <p style="margin:0 0 20px;font-family:Consolas,monospace;font-size:13px;word-break:break-all;background:#f4f6f5;border:1px solid #dfe5e2;border-radius:8px;padding:10px">${escape(token)}</p>
        <p style="margin:0 0 4px;font-size:13px;color:#4c5a55">Hiệu lực đến <strong>${escape(deadline)}</strong> và chỉ dùng được cho chính email này.</p>
        <p style="margin:0 0 24px;font-size:13px;color:#4c5a55">Nếu bạn không mong đợi email này, vui lòng bỏ qua.</p>
      </td></tr>
      <tr><td style="padding:0 28px 24px;border-top:1px solid #dfe5e2">
        <p style="margin:16px 0 0;font-size:12px;color:#77857f">EcoTrack — Hệ thống quản trị năng lượng tòa nhà thông minh</p>
      </td></tr>
    </table>
  </td></tr></table></body></html>`;
  return { subject, text, html, link };
}

async function sendInvitationEmail(payload) {
  const content = invitationTemplate(payload);
  if (!isConfigured()) {
    // Developer convenience: the link is visible in the server log instead.
    console.warn(`[mail] SMTP chưa cấu hình, không gửi được lời mời tới ${payload.to}. Liên kết: ${content.link}`);
    return { sent: false, reason: 'smtp_not_configured', detail: 'SMTP_HOST/SMTP_FROM chưa được cấu hình.', link: content.link };
  }
  try {
    await transport().sendMail({
      from: process.env.SMTP_FROM,
      to: payload.to,
      replyTo: process.env.SMTP_REPLY_TO || undefined,
      subject: content.subject,
      text: content.text,
      html: content.html,
    });
    return { sent: true, link: content.link };
  } catch (error) {
    // An invitation that exists but was not delivered is still usable by hand,
    // so a transport failure must not roll the request back.
    console.error(`[mail] Gửi lời mời tới ${payload.to} thất bại: ${error.message}`);
    // The column is bounded, and a transport message can be arbitrarily long.
    return { sent: false, reason: 'send_failed', detail: String(error.message || error).slice(0, 300), link: content.link };
  }
}

module.exports = { sendInvitationEmail, invitationTemplate, inviteUrl, isConfigured, useTransport, resetTransport };

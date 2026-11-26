const { randomBytes, createHash, scrypt: scryptCallback, timingSafeEqual } = require('crypto');
const { promisify } = require('util');
const prisma = require('../db');
const scrypt = promisify(scryptCallback);
const hashToken = (token) => createHash('sha256').update(token).digest('hex');
const SESSION_MS = 7 * 24 * 3600 * 1000;

async function hashPassword(password) {
  const salt = randomBytes(16).toString('hex');
  const derived = await scrypt(password, salt, 64, { N: 32768, r: 8, p: 1, maxmem: 64 * 1024 * 1024 });
  return `scrypt$${salt}$${derived.toString('hex')}`;
}
async function verifyPassword(password, stored) {
  const [, salt, hex] = stored.split('$');
  const actual = await scrypt(password, salt, 64, { N: 32768, r: 8, p: 1, maxmem: 64 * 1024 * 1024 });
  const expected = Buffer.from(hex, 'hex');
  return actual.length === expected.length && timingSafeEqual(actual, expected);
}
function sessionCookie(req, token, maxAge = SESSION_MS / 1000) {
  const secure = process.env.NODE_ENV === 'production' ? '; Secure' : '';
  return `ecotrack_session=${token}; HttpOnly; SameSite=Lax; Path=/; Max-Age=${maxAge}${secure}`;
}
function tokenFrom(req) {
  const item = (req.headers.cookie || '').split(';').map((value) => value.trim())
    .find((value) => value.startsWith('ecotrack_session='));
  const token = item?.slice('ecotrack_session='.length);
  return token && /^[a-f0-9]{64}$/.test(token) ? token : null;
}
async function resolveSession(req) {
  const token = tokenFrom(req);
  if (!token) return null;
  const session = await prisma.authSession.findUnique({
    where: { token_hash: hashToken(token) },
    include: { user: { include: { staff: { include: { building: true } },
      memberships: { include: { household: { include: { unit: { include: { building: true } } } } } } } } },
  });
  if (!session || session.expires_at <= new Date() || !session.user.active) return null;
  return session.user;
}
async function startSession(userId) {
  const token = randomBytes(32).toString('hex');
  await prisma.authSession.create({ data: { user_id: userId, token_hash: hashToken(token),
    expires_at: new Date(Date.now() + SESSION_MS) } });
  return token;
}
const isCurrent = (member, now = new Date()) => member.starts_at <= now
  && (!member.ends_at || member.ends_at > now)
  && member.household.starts_at <= now && (!member.household.ends_at || member.household.ends_at > now)
  && member.household.unit.active;

// Operator role: platform admin is ADMIN; building staff is MANAGER if any MANAGER row, else TECHNICIAN; residents have none.
function operatorRole(user) {
  if (user?.is_platform_admin) return 'ADMIN';
  const staff = user?.staff || [];
  if (staff.some((item) => item.role === 'MANAGER')) return 'MANAGER';
  return staff.length ? 'TECHNICIAN' : null;
}

function publicUser(user) {
  return { id: user.id, name: user.name, email: user.email, is_platform_admin: user.is_platform_admin,
    role: operatorRole(user),
    google_linked: Boolean(user.google_sub),
    staff: (user.staff || []).map((staff) => ({ building_id: staff.building_id, role: staff.role, building: staff.building })),
    households: (user.memberships || []).filter((member) => isCurrent(member)).map((member) => ({
      id: member.household_id, name: member.household.name, role: member.role,
      unit: member.household.unit,
    })),
  };
}
module.exports = { hashPassword, verifyPassword, hashToken, startSession, sessionCookie,
  tokenFrom, resolveSession, publicUser, isCurrent, operatorRole };

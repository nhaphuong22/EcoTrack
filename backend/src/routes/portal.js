const express = require('express');
const { z } = require('zod');
const { randomBytes, randomUUID } = require('crypto');
const prisma = require('../db');
const { access, overview, zones, manages, fail } = require('../services/portalService');
const { hashToken, isCurrent, resolveSession } = require('../services/authService');
const { sendInvitationEmail } = require('../services/mailService');
const { readingEmitter } = require('../services/readingStreamService');
const router = express.Router();
const wrap = (handler) => async (req, res, next) => { try { await handler(req, res); } catch (error) { next(error); } };
const emailSchema = z.string().trim().email().max(254).transform((value) => value.toLowerCase());

router.get('/overview', wrap(async (req, res) => {
  const context = await access(req.user, req.query);
  const limit = z.coerce.number().int().min(1).max(720).default(168).parse(req.query.limit);
  res.json(await overview(context, limit));
}));
router.get('/zones', wrap(async (req, res) => res.json(await zones(await access(req.user, req.query)))));
router.get('/buildings', wrap(async (req, res) => {
  const memberIds = (req.user.memberships || []).filter((member) => isCurrent(member))
    .map((member) => member.household.unit.building_id);
  const ids = [...new Set([...memberIds, ...(req.user.staff || []).map((staff) => staff.building_id)])];
  const buildings = await prisma.building.findMany({ where: req.user.is_platform_admin ? {} : { id: { in: ids } } });
  res.json({ buildings });
}));

router.get('/manage', wrap(async (req, res) => {
  const buildingId = z.string().min(1).max(50).parse(req.query.building_id);
  if (!manages(req.user, buildingId)) fail();
  const units = await prisma.unit.findMany({ where: { building_id: buildingId },
    include: { households: { include: { members: { select: { id: true, user_id: true, role: true,
      ends_at: true, user: { select: { name: true, email: true } } } },
      invitations: { where: { accepted_at: null, expires_at: { gt: new Date() } },
        select: { id: true, email: true, role: true, expires_at: true, email_sent_at: true,
          email_attempts: true, email_last_error: true }, orderBy: { expires_at: 'desc' } } } }, zones: true },
    orderBy: { code: 'asc' } });
  const unassigned = await prisma.zone.findMany({ where: { building_id: buildingId, unit_id: null }, include: { meter: true } });
  res.json({ units, unassigned_zones: unassigned });
}));
router.post('/units', wrap(async (req, res) => {
  const input = z.object({ building_id: z.string().min(1).max(50), code: z.string().trim().min(1).max(30),
    floor: z.number().int().min(-10).max(300).default(1), household_name: z.string().trim().min(1).max(100),
    zone_id: z.string().min(1).max(50).optional() }).parse(req.body);
  if (!manages(req.user, input.building_id)) fail();
  const result = await prisma.$transaction(async (tx) => {
    const unit = await tx.unit.create({ data: { building_id: input.building_id, code: input.code, floor: input.floor } });
    const household = await tx.household.create({ data: { unit_id: unit.id, name: input.household_name } });
    if (input.zone_id) {
      const changed = await tx.zone.updateMany({ where: { id: input.zone_id, building_id: input.building_id, unit_id: null },
        data: { unit_id: unit.id } });
      if (changed.count !== 1) fail('Zone is unavailable or belongs to another building.', 409);
      const meter = await tx.meter.updateMany({ where: { zone_id: input.zone_id, building_id: input.building_id,
        scope: 'UNASSIGNED', unit_id: null }, data: { scope: 'UNIT', unit_id: unit.id } });
      if (meter.count !== 1) fail('Only unassigned meters can be attached.', 409);
    }
    return { unit, household };
  });
  res.status(201).json(result);
}));
router.post('/units/:id/zones', wrap(async (req, res) => {
  const id = z.string().uuid().parse(req.params.id);
  const { zone_id } = z.object({ zone_id: z.string().min(1).max(50) }).parse(req.body);
  const unit = await prisma.unit.findUnique({ where: { id } });
  if (!unit || !manages(req.user, unit.building_id)) fail();
  await prisma.$transaction(async (tx) => {
    const zone = await tx.zone.updateMany({ where: { id: zone_id, building_id: unit.building_id, unit_id: null }, data: { unit_id: id } });
    if (zone.count !== 1) fail('Zone is unavailable.', 409);
    const meter = await tx.meter.updateMany({ where: { zone_id, building_id: unit.building_id, unit_id: null,
      scope: 'UNASSIGNED' }, data: { unit_id: id, scope: 'UNIT' } });
    if (meter.count !== 1) fail('Only unassigned meters can be attached.', 409);
  });
  res.json({ message: 'Meter attached to unit.' });
}));
router.post('/common-zones', wrap(async (req, res) => {
  const input = z.object({ building_id: z.string().min(1).max(50), zone_id: z.string().min(1).max(50) }).parse(req.body);
  if (!manages(req.user, input.building_id)) fail();
  const result = await prisma.meter.updateMany({ where: { building_id: input.building_id, zone_id: input.zone_id,
    unit_id: null, scope: 'UNASSIGNED' }, data: { scope: 'COMMON' } });
  if (result.count !== 1) fail('Only unassigned zones can become common areas.', 409);
  res.json({ message: 'Common area published.' });
}));
router.post('/invitations', wrap(async (req, res) => {
  const input = z.object({ household_id: z.string().uuid(), email: emailSchema,
    role: z.enum(['OWNER', 'MEMBER']).default('MEMBER') }).parse(req.body);
  const household = await prisma.household.findUnique({ where: { id: input.household_id },
    include: { unit: { include: { building: true } } } });
  if (!household || household.ends_at && household.ends_at <= new Date()) fail();
  const manager = manages(req.user, household.unit.building_id);
  const owner = (req.user.memberships || []).some((member) => member.household_id === input.household_id
    && member.role === 'OWNER' && isCurrent(member));
  if (!manager && (!owner || input.role !== 'MEMBER')) fail();
  const token = randomBytes(32).toString('hex');
  const invitation = await prisma.$transaction(async (tx) => {
    // A resend supersedes the outstanding invitation for the same invitee, so a
    // household and email never have two live tokens at once.
    const now = new Date();
    const superseded = await tx.invitation.updateMany({ where: { household_id: household.id, email: input.email,
      accepted_at: null, expires_at: { gt: now } }, data: { expires_at: now } });
    const created = await tx.invitation.create({ data: { household_id: household.id, email: input.email,
      role: input.role, token_hash: hashToken(token), created_by: req.user.id,
      expires_at: new Date(now.getTime() + 48 * 3600 * 1000) } });
    return { ...created, superseded: superseded.count };
  });
  // The invitee gets the link by email; the token is still returned so an
  // operator can pass it on by hand when mail delivery is unavailable.
  const mail = await sendInvitationEmail({ to: input.email, token, expiresAt: invitation.expires_at,
    role: input.role, householdName: household.name, unitCode: household.unit.code,
    buildingName: household.unit.building?.name, inviterName: req.user.name });
  try {
    await prisma.invitation.update({ where: { id: invitation.id }, data: { email_attempts: { increment: 1 },
      ...(mail.sent ? { email_sent_at: new Date(), email_last_error: null }
        : { email_last_error: `${mail.reason}: ${mail.detail || ''}`.slice(0, 300) }) } });
  } catch (error) {
    // Bookkeeping must never void an invitation that already exists, nor hide a
    // message that has already gone out.
    console.error(`[mail] Không ghi được trạng thái gửi lời mời ${invitation.id}: ${error.message}`);
  }
  res.status(201).json({ token, expires_at: invitation.expires_at, email: input.email,
    email_sent: mail.sent, superseded: invitation.superseded,
    ...(mail.sent ? {} : { email_error: mail.reason }) });
}));
router.post('/invitations/accept', wrap(async (req, res) => {
  const { token } = z.object({ token: z.string().regex(/^[a-f0-9]{64}$/) }).parse(req.body);
  const result = await prisma.$transaction(async (tx) => {
    const invitation = await tx.invitation.findUnique({ where: { token_hash: hashToken(token) },
      include: { household: { include: { unit: true } } } });
    const now = new Date();
    if (!invitation || invitation.email !== req.user.email || invitation.accepted_at
      || invitation.expires_at <= now || !invitation.household.unit.active
      || invitation.household.ends_at && invitation.household.ends_at <= now) fail('Invalid or expired invitation.', 403);
    const changed = await tx.invitation.updateMany({ where: { id: invitation.id, accepted_at: null, expires_at: { gt: now } },
      data: { accepted_at: now } });
    if (changed.count !== 1) fail('Invitation has already been used.', 409);
    // Create a new access period. Revocation expires outstanding invitations;
    // a deliberately issued fresh invitation does not restore the old period.
    return tx.householdMember.create({ data: { household_id: invitation.household_id, user_id: req.user.id,
      role: invitation.role, starts_at: now } });
  });
  res.status(201).json({ household_id: result.household_id });
}));
router.post('/members/:id/revoke', wrap(async (req, res) => {
  const id = z.string().uuid().parse(req.params.id);
  const member = await prisma.householdMember.findUnique({ where: { id }, include: { household: { include: { unit: true } } } });
  if (!member || !manages(req.user, member.household.unit.building_id)) fail();
  await prisma.householdMember.update({ where: { id }, data: { ends_at: new Date() } });
  // Unused invitations must not let the same email rejoin after revocation.
  const user = await prisma.user.findUnique({ where: { id: member.user_id } });
  await prisma.invitation.updateMany({ where: { household_id: member.household_id, email: user.email, accepted_at: null },
    data: { expires_at: new Date() } });
  res.json({ message: 'Membership revoked.' });
}));
router.post('/households/:id/end', wrap(async (req, res) => {
  const id = z.string().uuid().parse(req.params.id);
  const household = await prisma.household.findUnique({ where: { id }, include: { unit: true } });
  if (!household || !manages(req.user, household.unit.building_id)) fail();
  await prisma.household.update({ where: { id }, data: { ends_at: new Date() } });
  res.json({ message: 'Occupancy ended. Former residents no longer have access.' });
}));
router.post('/households', wrap(async (req, res) => {
  const input = z.object({ unit_id: z.string().uuid(), name: z.string().trim().min(1).max(100) }).parse(req.body);
  const unit = await prisma.unit.findUnique({ where: { id: input.unit_id } });
  if (!unit || !manages(req.user, unit.building_id)) fail();
  // The database also enforces one open occupancy per unit.
  res.status(201).json(await prisma.household.create({ data: input }));
}));

router.post('/chat', wrap(async (req, res) => {
  const input = z.object({ message: z.string().trim().min(1).max(4000), session_id: z.string().uuid().optional() }).parse(req.body);
  const context = await access(req.user, req.body);
  let session;
  if (input.session_id) {
    session = await prisma.chatSession.findFirst({ where: { id: input.session_id, user_id: req.user.id,
      building_id: context.building_id, household_id: context.household_id || null, scope: context.scope } });
    if (!session) fail();
    if (context.since && session.created_at < context.since) fail();
  } else {
    session = await prisma.chatSession.create({ data: { id: randomUUID(), user_id: req.user.id,
      building_id: context.building_id, household_id: context.household_id || null, scope: context.scope } });
  }
  // Never dispatch resident questions to the global replay tools. All figures
  // below have already passed household/time-window authorization.
  const data = await overview(context, 168);
  const reply = `Phạm vi: ${context.scope === 'household' ? context.household.name : context.scope === 'common' ? 'khu vực chung' : 'tổng tòa nhà'}. `
    + `Trong ${data.count} thời điểm có dữ liệu, tổng tiêu thụ là ${data.metrics.total_consumption_kwh.toFixed(2)} kWh. `
    + `Có ${data.anomalies.length} cảnh báo trong phạm vi được phép xem. `
    + 'Chưa có mô hình dự báo riêng cho phạm vi này; tôi không sử dụng số liệu của hộ khác để trả lời.';
  await prisma.conversation.createMany({ data: [
    { chat_id: session.id, session_id: session.id, building_id: context.building_id, role: 'user', message: input.message },
    { chat_id: session.id, session_id: session.id, building_id: context.building_id, role: 'assistant', message: reply },
  ] });
  res.json({ session_id: session.id, conversation_saved: true, reply, tools_used: ['authorized_household_metrics'] });
}));
router.get('/chats/:id', wrap(async (req, res) => {
  const id = z.string().uuid().parse(req.params.id);
  const chat = await prisma.chatSession.findFirst({ where: { id, user_id: req.user.id } });
  if (!chat) fail();
  const context = await access(req.user, chat);
  if (context.since && chat.created_at < context.since) fail();
  res.json({ messages: await prisma.conversation.findMany({ where: { chat_id: id }, orderBy: [{ created_at: 'asc' }, { id: 'asc' }] }) });
}));
router.get('/stream', wrap(async (req, res) => {
  await access(req.user, req.query);
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-store');
  res.setHeader('Connection', 'keep-alive');
  res.flushHeaders();
  let closed = false;
  const close = () => { if (closed) return; closed = true; clearInterval(heartbeat); readingEmitter.off('reading', listener); res.end(); };
  const authorize = async () => {
    const user = await resolveSession(req);
    if (!user) fail();
    return access(user, req.query);
  };
  const listener = async (reading) => {
    try {
      const context = await authorize();
      const timestamp = new Date(reading.timestamp);
      if (!closed && context.meters.some((meter) => meter.id === reading.meter_id)
        && (!context.since || timestamp >= context.since) && timestamp <= context.until) {
        res.write(`event: reading\ndata: ${JSON.stringify(reading)}\n\n`);
      }
    } catch { close(); }
  };
  const heartbeat = setInterval(async () => {
    try { await authorize(); if (!closed) res.write(': heartbeat\n\n'); } catch { close(); }
  }, 15000);
  heartbeat.unref?.();
  readingEmitter.on('reading', listener);
  req.on('close', close);
}));
module.exports = router;

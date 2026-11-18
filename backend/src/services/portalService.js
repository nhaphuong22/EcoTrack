const { z } = require('zod');
const prisma = require('../db');
const { isCurrent } = require('./authService');
const contextSchema = z.object({ scope: z.enum(['household', 'building', 'common']),
  building_id: z.string().min(1).max(50), household_id: z.string().uuid().nullish() });
function fail(message = 'Access denied.', status = 403) {
  const error = new Error(message); error.status = status; throw error;
}
function manages(user, buildingId) {
  return user.is_platform_admin || (user.staff || []).some((item) => item.building_id === buildingId && item.role === 'MANAGER');
}
async function access(user, input) {
  const context = contextSchema.parse(input);
  const now = new Date();
  const manager = manages(user, context.building_id);
  const members = (user.memberships || []).filter((member) => isCurrent(member, now)
    && member.household.unit.building_id === context.building_id);
  if (!manager && members.length === 0) fail();
  let household = null;
  let since = null;
  if (context.scope === 'household') {
    if (!context.household_id) fail('Select a household.', 422);
    const member = members.find((item) => item.household_id === context.household_id);
    if (member) {
      household = member.household;
      since = new Date(Math.max(member.starts_at.getTime(), household.starts_at.getTime()));
    } else if (manager) {
      household = await prisma.household.findUnique({ where: { id: context.household_id }, include: { unit: true } });
      if (!household || household.unit.building_id !== context.building_id) fail();
      since = household.starts_at;
    } else fail();
  }
  const meterWhere = { building_id: context.building_id,
    scope: context.scope === 'household' ? 'UNIT' : context.scope === 'common' ? 'COMMON' : 'BUILDING_TOTAL',
    ...(household ? { unit_id: household.unit_id } : {}),
  };
  const meters = await prisma.meter.findMany({ where: meterWhere });
  const until = household?.ends_at && household.ends_at < now ? household.ends_at : now;
  return { ...context, manager, household, since, until, meters,
    readingWhere: { meter_id: { in: meters.map((meter) => meter.id) },
      timestamp: { ...(since ? { gte: since } : {}), lte: until } },
  };
}
async function overview(context, limit = 168) {
  // Limit timestamps rather than letting many meters consume the whole history.
  const recentTimes = await prisma.meterReading.findMany({ where: context.readingWhere,
    select: { timestamp: true }, distinct: ['timestamp'], orderBy: { timestamp: 'desc' }, take: limit });
  const records = recentTimes.length ? await prisma.meterReading.findMany({
    where: { ...context.readingWhere, timestamp: { in: recentTimes.map((row) => row.timestamp) } },
    orderBy: { timestamp: 'asc' },
  }) : [];
  const points = new Map();
  for (const row of records) {
    const timestamp = row.timestamp.toISOString();
    const point = points.get(timestamp) || { timestamp, meter_reading_kwh: 0 };
    point.meter_reading_kwh += row.meter_reading_kwh;
    points.set(timestamp, point);
  }
  const data = [...points.values()];
  const total = data.reduce((sum, row) => sum + row.meter_reading_kwh, 0);
  const events = await prisma.anomalyEvent.findMany({ where: {
    building_id: context.building_id, meter_id: context.readingWhere.meter_id, timestamp: context.readingWhere.timestamp,
  }, orderBy: { timestamp: 'desc' }, take: 100 });
  return { building_id: context.building_id, household_id: context.household_id || null,
    scope: context.scope, source: 'database_demo', count: data.length, data,
    metrics: { building_id: context.building_id, total_consumption_kwh: total,
      peak_demand_kw: null, predicted_baseline_kwh: null,
      total_anomalies_detected: events.length, estimated_waste_cost_vnd: null, estimated_waste_cost_usd: null },
    anomalies: events.map((event) => ({ id: event.id, timestamp: event.timestamp.toISOString(),
      severity: event.severity, status: event.status, actual_kwh: event.actual_reading,
      anomaly_score: event.anomaly_score, suggested_action: event.suggested_action,
      predicted_kwh: event.snapshot?.predicted_kwh ?? null,
      delta_kwh: event.snapshot?.delta_kwh ?? null,
      estimated_waste_vnd: event.snapshot?.estimated_waste_vnd ?? null,
    })),
    forecast: [], forecast_available: false,
  };
}
async function zones(context) {
  const zoneIds = context.meters.map((meter) => meter.zone_id).filter(Boolean);
  const list = await prisma.zone.findMany({ where: { id: { in: zoneIds } }, orderBy: { id: 'asc' } });
  const result = [];
  for (const zone of list) {
    const latest = await prisma.meterReading.findFirst({ where: { ...context.readingWhere, zone_id: zone.id },
      orderBy: { timestamp: 'desc' } });
    result.push({ ...zone, latest_reading: latest });
  }
  return { building_id: context.building_id, total: result.length, zones: result };
}
module.exports = { access, manages, overview, zones, fail };

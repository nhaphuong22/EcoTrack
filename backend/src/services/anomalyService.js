const { randomUUID } = require('crypto');
const prisma = require('../db');
const { energyCache } = require('../utils/cache');
const { callAIService } = require('../utils/aiClient');
const { getHourlyBuildingSeries } = require('../utils/liveSeries');
const readingStreamService = require('./readingStreamService');

const VALID_STATUSES = ['OPEN', 'ACKNOWLEDGED', 'RESOLVED', 'IGNORED'];

function conflict() {
  const error = new Error('Incident changed during this update. Reload and try again.');
  error.status = 409;
  return error;
}

async function updateAnomalyStatus(anomalyId, status, note = null) {
  if (!VALID_STATUSES.includes(status)) {
    const error = new Error(`Invalid status: ${status}`);
    error.status = 422;
    throw error;
  }
  let record = await prisma.anomalyEvent.findUnique({ where: { id: anomalyId } });
  if (!record) {
    await syncAnomaliesFromAI();
    record = await prisma.anomalyEvent.findUnique({ where: { id: anomalyId } });
  }
  if (!record) {
    const error = new Error(`Anomaly incident with ID '${anomalyId}' not found.`);
    error.status = 404;
    throw error;
  }
  const updatedAt = new Date().toISOString();
  const history = Array.isArray(record.status_history) ? record.status_history : [];
  const nextHistory = [...history, {
    previous_status: record.status, status, note, updated_at: updatedAt,
    actor: 'operator',
  }];
  // Compare the audit history too: two notes on the same status must not overwrite.
  const result = await prisma.anomalyEvent.updateMany({
    where: { id: anomalyId, status: record.status, status_history: { equals: history } },
    data: { status, status_history: nextHistory },
  });
  if (result.count !== 1) throw conflict();
  energyCache.clear();
  return {
    id: anomalyId, previous_status: record.status, current_status: status,
    updated_at: updatedAt, note,
    message: `Incident status successfully updated from '${record.status}' to '${status}'.`,
  };
}

async function persistEvents(events) {
  for (const ev of events) {
    await prisma.anomalyEvent.upsert({
      where: { id: ev.id },
      // Preserve the original evidence, status, and notes on repeated detections.
      update: {},
      create: {
        id: ev.id, building_id: ev.building_id || 'office_tower_01',
        timestamp: new Date(ev.timestamp),
        actual_reading: ev.actual_kwh ?? ev.actual_reading ?? 0,
        anomaly_score: ev.anomaly_score ?? 0,
        severity: (ev.severity || 'LOW').toUpperCase(),
        suggested_action: ev.suggested_action || ev.description || null,
        status: 'OPEN', snapshot: ev, status_history: [],
      },
    });
  }
}

async function syncAnomaliesFromAI() {
  try {
    const events = await callAIService('/internal/anomalies/detect');
    if (Array.isArray(events)) await persistEvents(events);
  } catch (err) {
    console.warn('Could not sync anomalies from AI service:', err.message);
  }
}

function toEvent(record) {
  const snapshot = record.snapshot || {};
  return {
    // Legacy incidents have no model snapshot: unknown estimates stay unknown.
    subsystem: null, predicted_kwh: null, delta_kwh: null, outdoor_temp_c: null,
    estimated_waste_vnd: null, estimated_waste_usd: null, description: null,
    ...snapshot,
    id: record.id, building_id: record.building_id,
    timestamp: record.timestamp.toISOString(),
    severity: record.severity.charAt(0).toUpperCase() + record.severity.slice(1).toLowerCase(),
    actual_kwh: record.actual_reading, anomaly_score: record.anomaly_score,
    status: record.status, suggested_action: record.suggested_action,
    status_history: record.status_history || [],
  };
}

async function listAnomalies() {
  let rawEvents = [];
  try {
    const events = await callAIService('/internal/anomalies/detect');
    if (Array.isArray(events)) rawEvents = events;
  } catch (err) {
    console.warn('AI anomaly detection unavailable:', err.message);
  }
  try {
    await persistEvents(rawEvents);
  } catch (err) {
    console.warn('Could not persist detected incidents:', err.message);
  }
  // Union the current detection window and stored incidents. Unresolved incidents
  // must remain visible after they leave the model window.
  const merged = new Map(rawEvents.map((ev) => [ev.id, { ...ev, status: 'OPEN' }]));
  try {
    const records = await prisma.anomalyEvent.findMany({ orderBy: { timestamp: 'desc' } });
    for (const record of records) merged.set(record.id, toEvent(record));
  } catch (err) {
    console.warn('Incident persistence unavailable:', err.message);
  }
  return [...merged.values()].sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp));
}

const LIVE_COOLDOWN_MS = 10 * 60 * 1000;
const LIVE_MAX_AGE_MS = 15 * 60 * 1000;

async function evaluateLiveReadings(insertedReadings, intervalByKey = new Map()) {
  if (!Array.isArray(insertedReadings) || insertedReadings.length === 0 || insertedReadings.length > 20) {
    return [];
  }
  if (typeof prisma.anomalyEvent?.findFirst !== 'function' || typeof prisma.meterReading?.findMany !== 'function') {
    return [];
  }

  const nowMs = Date.now();
  const candidates = insertedReadings.filter((r) => {
    const tsMs = (r.timestamp instanceof Date ? r.timestamp : new Date(r.timestamp)).getTime();
    return Number.isFinite(tsMs) && Math.abs(nowMs - tsMs) <= LIVE_MAX_AGE_MS;
  });
  if (candidates.length === 0) return [];

  try {
    const bldgSeriesCache = new Map();
    const items = [];

    for (const r of candidates) {
      const ts = r.timestamp instanceof Date ? r.timestamp : new Date(r.timestamp);
      const tsIso = ts.toISOString();
      const key = `${r.building_id}:${r.zone_id || ''}:${tsIso}`;

      let bldgSeries = bldgSeriesCache.get(r.building_id);
      if (!bldgSeries) {
        bldgSeries = (await getHourlyBuildingSeries(r.building_id, 48)).map((p) => p.meter_reading_kwh);
        bldgSeriesCache.set(r.building_id, bldgSeries);
      }

      const prior = r.meter_id ? await prisma.meterReading.findMany({
        where: { meter_id: r.meter_id, timestamp: { lt: ts } },
        orderBy: { timestamp: 'desc' },
        take: 20,
      }) : [];

      let intervalSec = intervalByKey.get(key);
      if (!intervalSec && prior.length > 0) {
        const dt = (ts.getTime() - prior[0].timestamp.getTime()) / 1000;
        if (dt > 0 && dt <= 3600) intervalSec = dt;
      }
      if (!intervalSec) intervalSec = 3600;

      const meterHourlyKwhs = [];
      for (let i = 0; i < prior.length - 1; i += 1) {
        const dt = (prior[i].timestamp.getTime() - prior[i + 1].timestamp.getTime()) / 1000;
        if (dt >= 1 && dt <= 7200) {
          meterHourlyKwhs.push(prior[i].meter_reading_kwh * (3600 / Math.min(dt, 3600)));
        }
      }

      items.push({
        building_id: r.building_id,
        zone_id: r.zone_id || null,
        meter_id: r.meter_id || null,
        timestamp: tsIso,
        meter_reading_kwh: r.meter_reading_kwh,
        interval_seconds: intervalSec,
        outdoor_temperature_c: r.outdoor_temperature_c ?? null,
        recent_meter_hourly_kwhs: meterHourlyKwhs,
        recent_building_hourly_kwhs: bldgSeries,
      });
    }

    const flagged = await callAIService('/internal/anomalies/score', {
      method: 'POST',
      body: { items },
    });
    if (!Array.isArray(flagged) || flagged.length === 0) return [];

    const persisted = [];
    for (const ev of flagged) {
      const evTs = new Date(ev.timestamp);
      const cooldownSince = new Date(evTs.getTime() - LIVE_COOLDOWN_MS);
      const existing = ev.meter_id ? await prisma.anomalyEvent.findFirst({
        where: {
          building_id: ev.building_id,
          meter_id: ev.meter_id,
          status: 'OPEN',
          timestamp: { gte: cooldownSince },
        },
        orderBy: { timestamp: 'desc' },
      }) : null;

      if (existing) {
        if (ev.actual_kwh > existing.actual_reading && typeof prisma.anomalyEvent.update === 'function') {
          const updated = await prisma.anomalyEvent.update({
            where: { id: existing.id },
            data: {
              timestamp: evTs,
              actual_reading: ev.actual_kwh,
              anomaly_score: Math.max(existing.anomaly_score, ev.anomaly_score),
              severity: ev.severity,
              suggested_action: ev.suggested_action,
              snapshot: { ...ev, id: existing.id },
            },
          });
          const dto = toEvent(updated);
          readingStreamService.broadcastAnomaly(dto);
          persisted.push(dto);
        }
        continue;
      }

      const id = `ANOM-LIVE-${randomUUID().replace(/-/g, '').slice(0, 12)}`;
      const created = await prisma.anomalyEvent.create({
        data: {
          id,
          building_id: ev.building_id,
          meter_id: ev.meter_id || null,
          timestamp: evTs,
          actual_reading: ev.actual_kwh,
          anomaly_score: ev.anomaly_score,
          severity: ev.severity,
          suggested_action: ev.suggested_action || ev.description || null,
          status: 'OPEN',
          snapshot: { ...ev, id },
          status_history: [],
        },
      });
      const dto = toEvent(created);
      readingStreamService.broadcastAnomaly(dto);
      persisted.push(dto);
    }
    if (persisted.length > 0) energyCache.clear();
    return persisted;
  } catch (err) {
    console.warn('Live anomaly scoring skipped:', err.message);
    return [];
  }
}

module.exports = { updateAnomalyStatus, syncAnomaliesFromAI, listAnomalies, evaluateLiveReadings };

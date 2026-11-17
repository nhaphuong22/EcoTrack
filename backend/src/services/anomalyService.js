const prisma = require('../db');
const { callAIService } = require('../utils/aiClient');

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

module.exports = { updateAnomalyStatus, syncAnomaliesFromAI, listAnomalies };

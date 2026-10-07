const prisma = require('../db');
const { callAIService } = require('../utils/aiClient');

const VALID_STATUSES = ['OPEN', 'ACKNOWLEDGED', 'RESOLVED', 'IGNORED'];

async function updateAnomalyStatus(anomalyId, status, note = null) {
  if (!VALID_STATUSES.includes(status)) {
    const error = new Error(`Invalid status: ${status}. Must be one of: ${VALID_STATUSES.join(', ')}`);
    error.status = 422;
    throw error;
  }

  let eventRecord = await prisma.anomalyEvent.findUnique({
    where: { id: anomalyId },
  });

  // If not found, attempt to sync from AI Service detection first
  if (!eventRecord) {
    await syncAnomaliesFromAI();
    eventRecord = await prisma.anomalyEvent.findUnique({
      where: { id: anomalyId },
    });
  }

  if (!eventRecord) {
    const error = new Error(`Anomaly incident with ID '${anomalyId}' not found.`);
    error.status = 404;
    throw error;
  }

  const previousStatus = eventRecord.status;
  let suggestedAction = eventRecord.suggested_action;

  if (note) {
    const timestampStr = new Date().toISOString().replace('T', ' ').substring(0, 19) + ' UTC';
    const noteEntry = ` [${timestampStr} Note: ${note}]`;
    suggestedAction = suggestedAction ? suggestedAction + noteEntry : noteEntry;
  }

  const updatedRecord = await prisma.anomalyEvent.update({
    where: { id: anomalyId },
    data: {
      status,
      suggested_action: suggestedAction,
    },
  });

  return {
    id: anomalyId,
    previous_status: previousStatus,
    current_status: updatedRecord.status,
    updated_at: new Date().toISOString(),
    note: note || null,
    message: `Incident status successfully updated from '${previousStatus}' to '${status}'.`,
  };
}

async function syncAnomaliesFromAI() {
  try {
    const aiEvents = await callAIService('/internal/anomalies/detect');
    if (Array.isArray(aiEvents)) {
      for (const ev of aiEvents) {
        await prisma.anomalyEvent.upsert({
          where: { id: ev.id },
          update: {},
          create: {
            id: ev.id,
            building_id: ev.building_id || 'office_tower_01',
            timestamp: new Date(ev.timestamp),
            actual_reading: ev.actual_kwh || ev.actual_reading || 0,
            anomaly_score: ev.anomaly_score || 0,
            severity: (ev.severity || 'LOW').toUpperCase(),
            suggested_action: ev.suggested_action || ev.description || null,
            status: 'OPEN',
          },
        });
      }
    }
  } catch (err) {
    console.warn('Could not sync anomalies from AI service:', err.message);
  }
}

async function listAnomalies() {
  // 1. Fetch raw detected events from AI engine
  let rawEvents = [];
  try {
    rawEvents = await callAIService('/internal/anomalies/detect');
  } catch (err) {
    console.warn('AI anomaly detection failed or offline, falling back to DB records:', err.message);
  }

  // 2. Fetch persistent statuses from PostgreSQL
  const dbRecords = await prisma.anomalyEvent.findMany();
  const dbMap = new Map(dbRecords.map((r) => [r.id, r]));

  if (Array.isArray(rawEvents) && rawEvents.length > 0) {
    // Merge persistent DB status into AI events
    return rawEvents.map((ev) => {
      const dbItem = dbMap.get(ev.id);
      return {
        ...ev,
        status: dbItem ? dbItem.status : 'OPEN',
        suggested_action: dbItem && dbItem.suggested_action ? dbItem.suggested_action : ev.suggested_action,
      };
    });
  }

  // If AI was unreachable, return persistent DB records mapped to frontend schema
  return dbRecords.map((r) => ({
    id: r.id,
    timestamp: r.timestamp.toISOString(),
    subsystem: 'Chiller & HVAC Plant',
    severity: r.severity,
    anomaly_score: r.anomaly_score,
    actual_kwh: r.actual_reading,
    predicted_kwh: r.actual_reading * 0.8,
    delta_kwh: Number((r.actual_reading * 0.2).toFixed(1)),
    outdoor_temp_c: 28.0,
    estimated_waste_vnd: Math.round(r.actual_reading * 0.2 * 3100),
    estimated_waste_usd: Number((r.actual_reading * 0.2 * 0.125).toFixed(2)),
    status: r.status,
    description: 'Abnormal load deviation exceeding baseline prediction',
    suggested_action: r.suggested_action || 'Inspect chiller plant schedule and sub-meter power draw.',
  }));
}

module.exports = {
  updateAnomalyStatus,
  syncAnomaliesFromAI,
  listAnomalies,
};

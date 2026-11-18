// Integration verification against the configured PostgreSQL database.
// All fixture writes roll back, including when an assertion fails.
require('dotenv').config({ path: require('path').resolve(__dirname, '../.env') });
const assert = require('node:assert/strict');
const { randomUUID } = require('crypto');
const { PrismaClient } = require('@prisma/client');
const { readingEmitter } = require('../src/services/readingStreamService');
const { ingestReadings } = require('../src/services/ingestService');
const { getBuildingHistory, listZonesWithLatest } = require('../src/services/buildingService');
const { updateAnomalyStatus, listAnomalies } = require('../src/services/anomalyService');
const prisma = new PrismaClient();
const rollback = new Error('ROLLBACK_VERIFICATION_FIXTURES');
let checks = 0;

async function main() {
  try {
    await prisma.$transaction(async (tx) => {
      global.__mockPrisma = tx;
      const id = `verify-${randomUUID()}`;
      await tx.building.create({ data: { id, name: 'Temporary verification fixture' } });
      const zoneId = `z-${randomUUID()}`;
      await tx.zone.create({ data: { id: zoneId, building_id: id, name: 'Test room' } });
      const { meterId } = require('../src/services/meterService');
      await tx.meter.createMany({ data: [
        { id: meterId(id), building_id: id, name: 'total', scope: 'BUILDING_TOTAL' },
        { id: meterId(id, zoneId), building_id: id, zone_id: zoneId, name: 'room', scope: 'UNASSIGNED' },
      ] });
      const timestamp = new Date('2026-10-31T10:00:00Z');
      const total = { building_id: id, timestamp, meter_reading_kwh: 100 };
      const zoned = { ...total, zone_id: zoneId, meter_reading_kwh: 10 };
      const received = [];
      const listener = (row) => received.push(row);
      readingEmitter.on('reading', listener);
      try {
        assert.equal((await ingestReadings([total, zoned])).stored, 2);
        assert.equal((await ingestReadings([total, zoned])).stored, 0);
        assert.equal(received.length, 2);
        const newReading = { ...zoned, timestamp: new Date('2026-10-31T11:00:00Z'), meter_reading_kwh: 20 };
        assert.equal((await ingestReadings([{ ...zoned, meter_reading_kwh: 999 }, newReading])).stored, 1);
        assert.equal(received.length, 3);
        assert.equal(received[2].meter_reading_kwh, 20);
        checks += 3;
      } finally { readingEmitter.off('reading', listener); }

      const totals = await getBuildingHistory(id);
      const zoneHistory = await getBuildingHistory(id, 24, zoneId);
      assert.deepEqual(totals.data.map((row) => row.meter_reading_kwh), [100]);
      assert.deepEqual(zoneHistory.data.map((row) => row.meter_reading_kwh), [10, 20]);
      assert.equal(await tx.meterReading.count({ where: { building_id: id } }), 3);
      checks += 2;

      const otherId = `other-${randomUUID()}`;
      await tx.building.create({ data: { id: otherId, name: 'Empty building' } });
      assert.deepEqual((await listZonesWithLatest(otherId)).zones, []);
      await assert.rejects(ingestReadings([{ ...zoned, building_id: otherId }]), { status: 422 });
      checks += 2;

      const incidentId = `ANOM-${randomUUID()}`;
      const snapshot = { id: incidentId, building_id: id, timestamp: timestamp.toISOString(),
        actual_kwh: 100, predicted_kwh: 60, delta_kwh: 40, estimated_waste_vnd: 124000 };
      await tx.anomalyEvent.create({ data: { id: incidentId, building_id: id,
        timestamp, actual_reading: 100, anomaly_score: 0.9, severity: 'CRITICAL',
        suggested_action: 'Keep original advice', snapshot } });
      await updateAnomalyStatus(incidentId, 'ACKNOWLEDGED', 'Inspecting');
      await updateAnomalyStatus(incidentId, 'RESOLVED', 'Fixed');
      const incident = await tx.anomalyEvent.findUnique({ where: { id: incidentId } });
      assert.equal(incident.status_history.length, 2);
      assert.equal(incident.suggested_action, 'Keep original advice');
      assert.equal(incident.snapshot.predicted_kwh, 60);
      checks += 2;

      // A fake AI transport isolates only the network, keeping real DB reads/writes.
      const originalFetch = global.fetch;
      try {
        global.fetch = async () => ({ ok: true, status: 200, json: async () => [{
          ...snapshot, anomaly_score: 0.9, severity: 'Critical',
        }] });
        const incidents = await listAnomalies();
        assert.equal(incidents.find((row) => row.id === incidentId).status, 'RESOLVED');
        global.fetch = async () => { throw new Error('Simulated offline AI'); };
        const offline = (await listAnomalies()).find((row) => row.id === incidentId);
        assert.equal(offline.predicted_kwh, 60);
        assert.equal(offline.estimated_waste_vnd, 124000);
        checks += 2;
      } finally { global.fetch = originalFetch; }
      throw rollback;
    }, { timeout: 30000 });
  } catch (error) {
    if (error !== rollback) throw error;
  } finally {
    delete global.__mockPrisma;
    await prisma.$disconnect();
  }
  console.log(`PostgreSQL business verification: ${checks} checks passed; all fixture writes rolled back.`);
}
main().catch((error) => { console.error(error); process.exitCode = 1; });

const { createHash } = require('crypto');
const prisma = require('../db');
const meterId = (buildingId, zoneId = null) => 'meter-' + createHash('md5').update(`${buildingId}:${zoneId || 'total'}`).digest('hex');
async function initializeMeters() {
  const buildings = await prisma.building.findMany();
  const zones = await prisma.zone.findMany();
  for (const building of buildings) {
    await prisma.meter.upsert({ where: { id: meterId(building.id) }, update: {},
      create: { id: meterId(building.id), building_id: building.id, name: 'Building total', scope: 'BUILDING_TOTAL' } });
  }
  for (const zone of zones) {
    await prisma.meter.upsert({ where: { zone_id: zone.id }, update: {}, create: {
      id: meterId(zone.building_id, zone.id), building_id: zone.building_id,
      zone_id: zone.id, unit_id: zone.unit_id, name: zone.name, scope: zone.unit_id ? 'UNIT' : 'UNASSIGNED',
    } });
  }
}
module.exports = { meterId, initializeMeters };

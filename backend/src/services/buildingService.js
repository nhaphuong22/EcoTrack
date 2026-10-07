const prisma = require('../db');

const DEFAULT_BUILDINGS = [
  {
    id: 'office_tower_01',
    name: 'EcoTrack Headquarter Tower',
    building_type: 'Commercial Office',
    total_area_sqm: 15200.0,
    location: 'Hanoi, Vietnam',
    timezone: 'Asia/Ho_Chi_Minh',
  },
  {
    id: 'Hog_office_Betsy',
    name: 'Hog Betsy Benchmark Office (BDG2)',
    building_type: 'Office',
    total_area_sqm: 18450.0,
    location: 'Singapore',
    timezone: 'Asia/Singapore',
  },
];

let isSeeded = false;

async function seedDefaultBuildingsIfNeeded() {
  if (isSeeded) return;
  try {
    for (const b of DEFAULT_BUILDINGS) {
      await prisma.building.upsert({
        where: { id: b.id },
        update: {},
        create: b,
      });
      await seedInitialReadingsIfNeeded(b.id);
    }
    isSeeded = true;
  } catch (err) {
    // If DB is temporarily unreachable, allow future retry
    console.warn('Could not seed default buildings (DB might be offline):', err.message);
  }
}

async function seedInitialReadingsIfNeeded(buildingId, sampleHours = 72) {
  try {
    const existingCount = await prisma.meterReading.count({
      where: { building_id: buildingId },
    });

    if (existingCount >= 24) return;

    const baseTime = new Date();
    baseTime.setHours(baseTime.getHours() - sampleHours);

    const records = [];
    for (let h = 0; h < sampleHours; h++) {
      const t = new Date(baseTime.getTime() + h * 3600 * 1000);
      const hourOfDay = t.getUTCHours();
      const diurnal = hourOfDay >= 6 && hourOfDay <= 18
        ? Math.sin(((hourOfDay - 6) * Math.PI) / 12)
        : -0.5;
      const kwh = Math.max(50.0, Number((160.0 + diurnal * 80.0 + (h % 5)).toFixed(2)));
      const temp = Number((26.0 + diurnal * 5.0).toFixed(1));

      records.push({
        building_id: buildingId,
        timestamp: t,
        meter_reading_kwh: kwh,
        outdoor_temperature_c: temp,
        relative_humidity_pct: 72.0,
      });
    }

    if (records.length > 0) {
      await prisma.meterReading.createMany({
        data: records,
        skipDuplicates: true,
      });
    }
  } catch (err) {
    console.warn(`Could not seed readings for ${buildingId}:`, err.message);
  }
}

async function listBuildings() {
  await seedDefaultBuildingsIfNeeded();
  const buildings = await prisma.building.findMany({
    orderBy: { created_at: 'asc' },
  });
  return {
    total: buildings.length,
    buildings,
  };
}

async function getBuildingById(id) {
  await seedDefaultBuildingsIfNeeded();
  return await prisma.building.findUnique({
    where: { id },
  });
}

async function createBuilding(data) {
  return await prisma.building.create({
    data,
  });
}

async function getBuildingHistory(buildingId, limit = 168) {
  await seedDefaultBuildingsIfNeeded();
  const building = await prisma.building.findUnique({
    where: { id: buildingId },
  });

  if (!building) return null;

  await seedInitialReadingsIfNeeded(buildingId);

  const readings = await prisma.meterReading.findMany({
    where: { building_id: buildingId },
    orderBy: { timestamp: 'desc' },
    take: limit,
  });

  const chronological = readings.reverse();

  return {
    building_id: buildingId,
    count: chronological.length,
    data: chronological.map((r) => ({
      timestamp: r.timestamp.toISOString(),
      meter_reading_kwh: r.meter_reading_kwh,
      outdoor_temperature_c: r.outdoor_temperature_c,
      relative_humidity_pct: r.relative_humidity_pct,
    })),
  };
}

module.exports = {
  seedDefaultBuildingsIfNeeded,
  seedInitialReadingsIfNeeded,
  listBuildings,
  getBuildingById,
  createBuilding,
  getBuildingHistory,
};

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

const DEFAULT_ZONES_OFFICE_01 = Array.from({ length: 10 }, (_, i) => ({
  id: `z${i + 1}`,
  building_id: 'office_tower_01',
  floor: 1,
  name: `Tầng 1 - Phòng ${101 + i}`,
}));

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
    if (prisma.zone && typeof prisma.zone.upsert === 'function') {
      for (const z of DEFAULT_ZONES_OFFICE_01) {
        await prisma.zone.upsert({
          where: { id: z.id },
          update: {},
          create: z,
        });
      }
    }
    isSeeded = true;
  } catch (err) {
    // If DB is temporarily unreachable, allow future retry
    console.warn('Could not seed default buildings (DB might be offline):', err.message);
  }
}

async function seedInitialReadingsIfNeeded(buildingId, sampleHours = 72) {
  if (!DEFAULT_BUILDINGS.some((b) => b.id === buildingId)) return;
  try {
    const existingCount = await prisma.meterReading.count({
      where: { building_id: buildingId },
    });

    if (existingCount > 0) return;

    const { meterId } = require('./meterService');
    const totalMeterId = meterId(buildingId);
    await prisma.meter.upsert({ where: { id: totalMeterId }, update: {}, create: {
      id: totalMeterId, building_id: buildingId, name: 'Building total', scope: 'BUILDING_TOTAL',
    } });

    const baseTime = new Date();
    baseTime.setUTCMinutes(0, 0, 0);
    baseTime.setUTCHours(baseTime.getUTCHours() - sampleHours);

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
        meter_id: totalMeterId,
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
  try {
    const buildings = await prisma.building.findMany({
      orderBy: { created_at: 'asc' },
    });
    return {
      total: buildings.length,
      buildings,
    };
  } catch (err) {
    return {
      total: DEFAULT_BUILDINGS.length,
      buildings: DEFAULT_BUILDINGS,
    };
  }
}

async function getBuildingById(id) {
  try {
    const building = await prisma.building.findUnique({
      where: { id },
    });
    return building;
  } catch (err) {
    // Database offline fallback
  }
  return DEFAULT_BUILDINGS.find((b) => b.id === id) || null;
}

async function createBuilding(data) {
  const { meterId } = require('./meterService');
  return prisma.$transaction(async (tx) => {
    const building = await tx.building.create({ data });
    await tx.meter.create({ data: { id: meterId(building.id), building_id: building.id,
      name: 'Building total', scope: 'BUILDING_TOTAL' } });
    return building;
  });
}

async function getBuildingHistory(buildingId, limit = 168, zoneId = null) {
  try {
    const building = await prisma.building.findUnique({
      where: { id: buildingId },
    });

    if (!building) return null;
    if (building) {
      if (zoneId) {
        const zone = await prisma.zone.findFirst({ where: { id: zoneId, building_id: buildingId } });
        if (!zone) return null;
      }
      const readings = await prisma.meterReading.findMany({
        where: { building_id: buildingId, zone_id: zoneId },
        orderBy: { timestamp: 'desc' },
        take: limit,
      });

      const chronological = readings.reverse();

      return {
        building_id: buildingId,
        zone_id: zoneId,
        source: 'database',
        count: chronological.length,
        data: chronological.map((r) => ({
          zone_id: r.zone_id ?? null,
          timestamp: r.timestamp.toISOString(),
          meter_reading_kwh: r.meter_reading_kwh,
          outdoor_temperature_c: r.outdoor_temperature_c,
          relative_humidity_pct: r.relative_humidity_pct,
        })),
      };
    }
  } catch (err) {
    // Database offline fallback
  }

  // If DB query returned no building or failed, check DEFAULT_BUILDINGS
  const knownBuilding = DEFAULT_BUILDINGS.find((b) => b.id === buildingId);
  if (!knownBuilding) return null;

  if (zoneId) return { building_id: buildingId, zone_id: zoneId, source: 'demo_fallback', count: 0, data: [] };

  // Fallback synthetic history
  const baseTime = new Date();
  baseTime.setHours(baseTime.getHours() - 72);
  const fallbackRecords = [];
  for (let h = 0; h < 72; h++) {
    const t = new Date(baseTime.getTime() + h * 3600 * 1000);
    const hourOfDay = t.getUTCHours();
    const diurnal = hourOfDay >= 6 && hourOfDay <= 18 ? Math.sin(((hourOfDay - 6) * Math.PI) / 12) : -0.5;
    fallbackRecords.push({
      timestamp: t.toISOString(),
      meter_reading_kwh: Math.max(50.0, Number((160.0 + diurnal * 80.0 + (h % 5)).toFixed(2))),
      outdoor_temperature_c: Number((26.0 + diurnal * 5.0).toFixed(1)),
      relative_humidity_pct: 72.0,
    });
  }

  const limitedRecords = fallbackRecords.slice(-limit);
  return {
    building_id: buildingId,
    zone_id: null,
    source: 'demo_fallback',
    count: limitedRecords.length,
    data: limitedRecords,
  };
}

async function listZonesWithLatest(buildingId) {
  try {
    const building = await prisma.building.findUnique({
      where: { id: buildingId },
    });

    if (!building) return null;
    if (building) {
      const zones = await prisma.zone.findMany({
        where: { building_id: buildingId },
        include: {
          meter_readings: {
            orderBy: { timestamp: 'desc' },
            take: 1,
          },
        },
        orderBy: { id: 'asc' },
      });

      if (zones) {
        return {
          building_id: buildingId,
          source: 'database',
          total: zones.length,
          zones: zones.map((z) => {
            const latest = z.meter_readings && z.meter_readings.length > 0 ? z.meter_readings[0] : null;
            const reading = latest || z.latest_reading || null;
            return {
              id: z.id,
              building_id: z.building_id,
              floor: z.floor,
              name: z.name,
              created_at: z.created_at,
              latest_reading: reading
                ? {
                    timestamp: reading.timestamp instanceof Date ? reading.timestamp.toISOString() : reading.timestamp,
                    meter_reading_kwh: reading.meter_reading_kwh,
                    outdoor_temperature_c: reading.outdoor_temperature_c ?? null,
                    relative_humidity_pct: reading.relative_humidity_pct ?? null,
                  }
                : null,
            };
          }),
        };
      }
    }
  } catch (err) {
    // Database offline, use DEFAULT_ZONES_OFFICE_01
  }

  // If DB query returned no building or failed, check DEFAULT_BUILDINGS
  const knownBuilding = DEFAULT_BUILDINGS.find((b) => b.id === buildingId);
  if (!knownBuilding) return null;

  const fallbackZones = DEFAULT_ZONES_OFFICE_01.filter((z) => z.building_id === buildingId);

  // Graceful in-memory fallback for Zones
  return {
    building_id: buildingId,
    source: 'demo_fallback',
    total: fallbackZones.length,
    zones: fallbackZones.map((z) => ({
      id: z.id,
      building_id: z.building_id,
      floor: z.floor,
      name: z.name,
      created_at: new Date().toISOString(),
      latest_reading: {
        timestamp: new Date().toISOString(),
        meter_reading_kwh: Number((110 + Math.random() * 60).toFixed(1)),
        outdoor_temperature_c: 28.5,
        relative_humidity_pct: 65.0,
      },
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
  listZonesWithLatest,
};

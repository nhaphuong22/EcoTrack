const fs = require('fs');
const path = require('path');
require('dotenv').config({ path: path.resolve(__dirname, '../../.env') });

// 10 zones matching office_tower_01 seed
const ZONES = Array.from({ length: 10 }, (_, i) => `z${i + 1}`);
const ZONE_MULTIPLIERS = [0.08, 0.12, 0.09, 0.11, 0.10, 0.14, 0.07, 0.13, 0.06, 0.10];
const TEMP_OFFSETS = [-1.0, -0.7, -0.4, -0.2, 0.0, 0.3, 0.5, 0.8, 1.0, 1.2];
const HOUR_MS = 3600000;

// Realistic 24-hour curves ([total_kwh_per_hour_10_zones, outdoor_temp_c]) aligned to local time-of-day.
const HOURLY_PROFILES = {
  office: [
    [78, 24.5], [74, 24.0], [72, 23.8], [70, 23.5], [72, 23.5], [82, 24.0],
    [118, 25.0], [175, 26.2], [235, 27.8], [265, 29.2], [278, 30.5], [268, 31.6],
    [210, 32.4], [248, 32.8], [282, 32.5], [286, 31.8], [272, 30.8], [228, 29.5],
    [168, 28.4], [132, 27.4], [112, 26.6], [96, 25.8], [86, 25.2], [80, 24.8],
  ],
  household: [
    [5.2, 24.5], [4.5, 24.0], [4.2, 23.8], [4.0, 23.5], [4.3, 23.5], [6.5, 24.0],
    [14.0, 25.0], [18.5, 26.2], [11.0, 27.8], [8.5, 29.2], [8.0, 30.5], [10.5, 31.6],
    [13.0, 32.4], [10.0, 32.8], [8.5, 32.5], [9.5, 31.8], [13.5, 30.8], [21.0, 29.5],
    [28.5, 28.4], [31.0, 27.4], [29.0, 26.6], [23.5, 25.8], [14.0, 25.2], [7.8, 24.8],
  ],
};

const WEEKDAY_MAP = { Mon: 0, Tue: 1, Wed: 2, Thu: 3, Fri: 4, Sat: 5, Sun: 6 };

function getTimePartsInZone(date = new Date(), timeZone = 'Asia/Ho_Chi_Minh') {
  try {
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone,
      weekday: 'short',
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23',
    }).formatToParts(date);
    const map = Object.fromEntries(parts.map((p) => [p.type, p.value]));
    const hour = Math.min(23, Math.max(0, parseInt(map.hour, 10) || 0));
    const minute = Math.min(59, Math.max(0, parseInt(map.minute, 10) || 0));
    const dayOfWeek = WEEKDAY_MAP[map.weekday] ?? ((date.getUTCDay() + 6) % 7);
    return { hour, minute, dayOfWeek, isWeekend: dayOfWeek >= 5 };
  } catch {
    const hour = date.getUTCHours();
    const minute = date.getUTCMinutes();
    const dayOfWeek = (date.getUTCDay() + 6) % 7;
    return { hour, minute, dayOfWeek, isWeekend: dayOfWeek >= 5 };
  }
}

function loadDataRows() {
  const root = path.resolve(__dirname, '../../../');
  const csvPath = path.join(root, 'ai-service/data/processed/office_building_clean.csv');
  const jsonPath = path.join(root, 'ai-service/data/sample_bdg2_energy.json');

  if (fs.existsSync(csvPath)) {
    try {
      const content = fs.readFileSync(csvPath, 'utf8');
      const lines = content.trim().split('\n');
      const rows = [];
      for (let i = 1; i < lines.length; i++) {
        const line = lines[i].trim();
        if (!line) continue;
        const [ts, reading, temp] = line.split(',');
        const kwh = parseFloat(reading);
        const t = parseFloat(temp);
        if (!isNaN(kwh)) {
          rows.push({
            timestamp: ts,
            meter_reading: kwh,
            air_temperature: isNaN(t) ? 26.0 : t,
          });
        }
      }
      if (rows.length > 0) return rows;
    } catch (e) {
      console.warn('[Simulator] Error reading CSV, checking JSON fallback:', e.message);
    }
  }

  if (fs.existsSync(jsonPath)) {
    try {
      const content = fs.readFileSync(jsonPath, 'utf8');
      const data = JSON.parse(content);
      const items = Array.isArray(data) ? data : data.data || [];
      return items.map((r) => ({
        timestamp: r.timestamp,
        meter_reading: r.meter_reading || r.meter_reading_kwh || 150.0,
        air_temperature: r.air_temperature || r.outdoor_temperature_c || 26.0,
      }));
    } catch (e) {
      console.warn('[Simulator] Error reading JSON fallback:', e.message);
    }
  }

  // ponytail: minimal synthetic fallback if no dataset exists
  return Array.from({ length: 24 }, (_, h) => ({
    meter_reading: HOURLY_PROFILES.office[h][0],
    air_temperature: HOURLY_PROFILES.office[h][1],
  }));
}

function indexCsvByDayHour(rows) {
  const byDayHour = new Map();
  const byHour = Array.from({ length: 24 }, () => []);
  for (const row of rows) {
    if (!row.timestamp) continue;
    const d = new Date(String(row.timestamp).replace(' ', 'T') + (String(row.timestamp).includes('Z') ? '' : 'Z'));
    if (Number.isNaN(d.getTime())) continue;
    const hour = d.getUTCHours();
    const dow = (d.getUTCDay() + 6) % 7;
    const key = `${dow}-${hour}`;
    if (!byDayHour.has(key)) byDayHour.set(key, []);
    byDayHour.get(key).push(row);
    byHour[hour].push(row);
  }
  return { byDayHour, byHour };
}

function sampleTimeAlignedRow(date = new Date(), options = {}, csvIndex = null, rng = Math.random) {
  const { hour, minute, dayOfWeek, isWeekend } = getTimePartsInZone(date, options.timeZone || 'Asia/Ho_Chi_Minh');
  const nextHour = (hour + 1) % 24;
  const nextDayOfWeek = hour === 23 ? (dayOfWeek + 1) % 7 : dayOfWeek;
  const frac = minute / 60;

  let kwh;
  let temp;

  if (options.profile === 'csv' && csvIndex) {
    const pick = (dow, h) => {
      const list = csvIndex.byDayHour.get(`${dow}-${h}`);
      const pool = list && list.length ? list : csvIndex.byHour[h];
      if (!pool || !pool.length) return null;
      return pool[Math.floor(rng() * pool.length)];
    };
    const curr = pick(dayOfWeek, hour);
    const next = pick(nextDayOfWeek, nextHour) || curr;
    if (curr) {
      kwh = curr.meter_reading * (1 - frac) + next.meter_reading * frac;
      temp = curr.air_temperature * (1 - frac) + next.air_temperature * frac;
    }
  }

  if (kwh === undefined) {
    const curve = HOURLY_PROFILES[options.profile] || HOURLY_PROFILES.office;
    const [kwh0, temp0] = curve[hour];
    const [kwh1, temp1] = curve[nextHour];
    kwh = kwh0 * (1 - frac) + kwh1 * frac;
    temp = temp0 * (1 - frac) + temp1 * frac;
    if ((options.profile || 'office') === 'office' && isWeekend) {
      kwh *= 0.45;
    }
  }

  if (options.jitter !== false) {
    const factor = 1 + (rng() - 0.5) * 0.06;
    kwh *= factor;
  }

  return {
    meter_reading: Number(Math.max(1.0, kwh).toFixed(2)),
    air_temperature: Number(temp.toFixed(1)),
  };
}

function parseArgs(args = process.argv.slice(2)) {
  const options = {
    anomalyZone: null,
    intervalMs: 3000,
    buildingId: 'office_tower_01',
    gatewayUrl: process.env.GATEWAY_URL || 'http://localhost:5000',
    apiKey: process.env.INGEST_API_KEY,
    profile: 'office',
    timeZone: process.env.APP_TIMEZONE || 'Asia/Ho_Chi_Minh',
    backfillHours: 0,
    includeBuildingTotal: true,
    jitter: true,
    once: false,
    maxTicks: Infinity,
  };

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === '--anomaly-zone' && args[i + 1]) {
      options.anomalyZone = args[++i];
    } else if (arg === '--interval' && args[i + 1]) {
      options.intervalMs = parseInt(args[++i], 10);
    } else if (arg === '--building' && args[i + 1]) {
      options.buildingId = args[++i];
    } else if (arg === '--gateway-url' && args[i + 1]) {
      options.gatewayUrl = args[++i];
    } else if (arg === '--api-key' && args[i + 1]) {
      options.apiKey = args[++i];
    } else if (arg === '--profile' && args[i + 1]) {
      options.profile = args[++i];
    } else if (arg === '--tz' && args[i + 1]) {
      options.timeZone = args[++i];
    } else if (arg === '--backfill-hours' && args[i + 1]) {
      options.backfillHours = Math.min(168, Math.max(0, parseInt(args[++i], 10) || 0));
    } else if (arg === '--no-building-total') {
      options.includeBuildingTotal = false;
    } else if (arg === '--no-jitter') {
      options.jitter = false;
    } else if (arg === '--fleet') {
      options.fleet = true;
    } else if (arg === '--wait') {
      options.waitForGateway = true;
    } else if (arg === '--once') {
      options.once = true;
    } else if (arg === '--count' && args[i + 1]) {
      options.maxTicks = parseInt(args[++i], 10);
    }
  }

  return options;
}

function generateBatch(row, options = {}, timestamp = new Date().toISOString()) {
  const totalReading = row.meter_reading || 150.0;
  const baseTemp = row.air_temperature || 26.0;
  // Source rows represent hourly kWh; scale to the actual tick interval so summed readings stay physically accurate.
  const intervalMs = Number.isFinite(options?.intervalMs) && options.intervalMs > 0 ? options.intervalMs : 3000;
  const intervalScale = intervalMs / HOUR_MS;
  const intervalSeconds = Number((intervalMs / 1000).toFixed(3));

  const zones = options.zones || ZONES;
  const shares = options.zoneShares || ZONE_MULTIPLIERS;
  const items = zones.map((zoneId, idx) => {
    let kwh = Math.max(0.0001, Number((totalReading * shares[idx] * intervalScale).toFixed(4)));
    let temp = Number((baseTemp + (TEMP_OFFSETS[idx] ?? 0)).toFixed(1));

    if (options.anomalyZone && zoneId === options.anomalyZone) {
      kwh = Number((kwh * 2.5).toFixed(4));
      temp = Number((temp + 8.5).toFixed(1));
    }

    return {
      building_id: options.buildingId,
      zone_id: zoneId,
      timestamp,
      meter_reading_kwh: kwh,
      interval_seconds: intervalSeconds,
      outdoor_temperature_c: temp,
      relative_humidity_pct: 70.0,
    };
  });

  if (options.includeBuildingTotal === true) {
    const totalKwh = Number(items.reduce((sum, item) => sum + item.meter_reading_kwh, 0).toFixed(4));
    const avgTemp = Number((items.reduce((sum, item) => sum + item.outdoor_temperature_c, 0) / items.length).toFixed(1));
    items.push({
      building_id: options.buildingId,
      zone_id: null,
      timestamp,
      meter_reading_kwh: totalKwh,
      interval_seconds: intervalSeconds,
      outdoor_temperature_c: avgTemp,
      relative_humidity_pct: 70.0,
    });
  }

  return items;
}

async function sendBatch(batch, options) {
  const endpoint = `${options.gatewayUrl.replace(/\/$/, '')}/api/v1/ingest/readings`;
  try {
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Ingest-Key': options.apiKey,
      },
      body: JSON.stringify(batch),
    });

    if (res.ok) {
      const data = await res.json();
      console.log(`[Simulator] Successfully posted ${batch.length} zone readings (stored: ${data.stored})`);
      return { success: true, stored: data.stored };
    } else {
      const text = await res.text();
      console.warn(`[Simulator] Ingest rejected (${res.status}): ${text}`);
      return { success: false, status: res.status };
    }
  } catch (err) {
    console.warn(`[Simulator] Gateway unreachable at ${endpoint}: ${err.message}. Will retry next tick.`);
    return { success: false, error: err.message };
  }
}

async function seedBackfill(options, csvIndex = null, now = new Date()) {
  if (!options.backfillHours || options.backfillHours <= 0) return 0;
  const currentHourStart = new Date(Date.UTC(
    now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), now.getUTCHours(), 0, 0, 0
  ));
  const hourlyOpts = { ...options, intervalMs: HOUR_MS, anomalyZone: null };
  const allItems = [];
  for (let h = options.backfillHours; h >= 1; h--) {
    const tsDate = new Date(currentHourStart.getTime() - h * HOUR_MS);
    const row = sampleTimeAlignedRow(tsDate, options, csvIndex);
    allItems.push(...generateBatch(row, hourlyOpts, tsDate.toISOString()));
  }

  let totalStored = 0;
  for (let i = 0; i < allItems.length; i += 200) {
    const chunk = allItems.slice(i, i + 200);
    const res = await sendBatch(chunk, options);
    if (res.success && typeof res.stored === 'number') totalStored += res.stored;
  }
  console.log(`[Simulator] Backfilled ${options.backfillHours}h time-aligned history (${totalStored} readings stored).`);
  return totalStored;
}

// Households vary in size; derive a stable 0.6-1.4 factor from the zone id so each hộ keeps its own scale.
function householdShare(zoneId) {
  let h = 0;
  for (const c of zoneId) h = (h * 31 + c.charCodeAt(0)) % 1000;
  return 0.6 + (h / 1000) * 0.8;
}

async function fetchTargets(opts) {
  const res = await fetch(`${opts.gatewayUrl.replace(/\/$/, '')}/api/v1/ingest/targets`, { headers: { 'X-Ingest-Key': opts.apiKey } });
  if (!res.ok) throw new Error(`targets ${res.status}`);
  return (await res.json()).buildings;
}

// Streams only what the gateway says should have data: re-read every tick so a household added by a manager starts producing
// readings on the next tick. shortcut: a household added later gets no backfilled history, add per-zone backfill if needed.
async function runFleet(opts) {
  const backfilled = new Set();
  let tickCount = 0;
  console.log(`[Simulator] Fleet mode: following buildings and households registered in the gateway (interval: ${opts.intervalMs}ms)`);

  const tick = async () => {
    tickCount++;
    let buildings = [];
    try { buildings = await fetchTargets(opts); } catch (err) { console.warn(`[Simulator] Could not load targets: ${err.message}`); }
    const now = new Date();
    for (const b of buildings) {
      if (!b.zones.length) continue;
      const residential = b.building_type === 'Residential';
      const o = { ...opts, fleet: false, buildingId: b.id, timeZone: b.timezone || opts.timeZone,
        profile: residential ? 'household' : 'office', zones: b.zones,
        zoneShares: b.zones.map((z) => (residential ? householdShare(z) : ZONE_MULTIPLIERS[ZONES.indexOf(z)] ?? 0.1)) };
      if (opts.backfillHours > 0 && !backfilled.has(b.id)) { backfilled.add(b.id); await seedBackfill(o); }
      await sendBatch(generateBatch(sampleTimeAlignedRow(now, o), o, now.toISOString()), o);
    }
    if (!opts.once && tickCount < opts.maxTicks) setTimeout(tick, opts.intervalMs);
  };
  await tick();
}

async function runSimulator(options = {}) {
  const opts = { ...parseArgs([]), ...options };
  if (!opts.apiKey) throw new Error('INGEST_API_KEY or --api-key is required.');
  const csvIndex = opts.profile === 'csv' ? indexCsvByDayHour(loadDataRows()) : null;
  let tickCount = 0;

  // Started alongside the gateway by `npm run dev`: wait until it accepts connections (any HTTP status counts).
  if (opts.waitForGateway) {
    for (let i = 0; i < 120; i++) {
      try { await fetch(opts.gatewayUrl); break; } catch { await new Promise((r) => setTimeout(r, 1000)); }
    }
  }

  if (opts.fleet) return runFleet(opts);

  if (opts.backfillHours > 0) {
    await seedBackfill(opts, csvIndex);
  }

  console.log(
    `[Simulator] Starting ${opts.profile} simulator for ${opts.buildingId} (${(opts.zones || ZONES).length} zones, tz: ${opts.timeZone}, interval: ${opts.intervalMs}ms)`
  );
  if (opts.anomalyZone) {
    console.log(`[Simulator] Injecting anomaly into zone: ${opts.anomalyZone}`);
  }

  const tick = async () => {
    tickCount++;
    const now = new Date();
    const row = sampleTimeAlignedRow(now, opts, csvIndex);
    const batch = generateBatch(row, opts, now.toISOString());
    await sendBatch(batch, opts);

    if (opts.once || tickCount >= opts.maxTicks) {
      return;
    }
    setTimeout(tick, opts.intervalMs);
  };

  await tick();
}

if (require.main === module) {
  const options = parseArgs();
  runSimulator(options);
}

module.exports = {
  ZONES,
  HOURLY_PROFILES,
  HOUR_MS,
  getTimePartsInZone,
  loadDataRows,
  indexCsvByDayHour,
  sampleTimeAlignedRow,
  generateBatch,
  sendBatch,
  seedBackfill,
  runSimulator,
  runFleet,
  parseArgs,
};

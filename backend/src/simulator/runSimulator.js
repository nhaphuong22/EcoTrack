const fs = require('fs');
const path = require('path');

// 10 zones matching office_tower_01 seed
const ZONES = Array.from({ length: 10 }, (_, i) => `z${i + 1}`);
const ZONE_MULTIPLIERS = [0.08, 0.12, 0.09, 0.11, 0.10, 0.14, 0.07, 0.13, 0.06, 0.10];
const TEMP_OFFSETS = [-1.0, -0.7, -0.4, -0.2, 0.0, 0.3, 0.5, 0.8, 1.0, 1.2];

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
        meter_reading: r.meter_reading || r.meter_reading_kwh || 150.0,
        air_temperature: r.air_temperature || r.outdoor_temperature_c || 26.0,
      }));
    } catch (e) {
      console.warn('[Simulator] Error reading JSON fallback:', e.message);
    }
  }

  // ponytail: minimal synthetic fallback if no dataset exists
  return Array.from({ length: 24 }, (_, h) => ({
    meter_reading: 150.0 + Math.sin(h / 3) * 50.0,
    air_temperature: 28.0 + Math.sin(h / 4) * 4.0,
  }));
}

function parseArgs(args = process.argv.slice(2)) {
  const options = {
    anomalyZone: null,
    intervalMs: 3000,
    buildingId: 'office_tower_01',
    gatewayUrl: process.env.GATEWAY_URL || 'http://localhost:5000',
    apiKey: process.env.INGEST_API_KEY || 'ecotrack_ingest_secret_2026',
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
    } else if (arg === '--once') {
      options.once = true;
    } else if (arg === '--count' && args[i + 1]) {
      options.maxTicks = parseInt(args[++i], 10);
    }
  }

  return options;
}

function generateBatch(row, options, timestamp = new Date().toISOString()) {
  const totalReading = row.meter_reading || 150.0;
  const baseTemp = row.air_temperature || 26.0;

  return ZONES.map((zoneId, idx) => {
    let kwh = Number((totalReading * ZONE_MULTIPLIERS[idx]).toFixed(2));
    let temp = Number((baseTemp + TEMP_OFFSETS[idx]).toFixed(1));

    if (options.anomalyZone && zoneId === options.anomalyZone) {
      kwh = Number((kwh * 2.5).toFixed(2));
      temp = Number((temp + 8.5).toFixed(1));
    }

    return {
      building_id: options.buildingId,
      zone_id: zoneId,
      timestamp,
      meter_reading_kwh: kwh,
      outdoor_temperature_c: temp,
      relative_humidity_pct: 70.0,
    };
  });
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

async function runSimulator(options = {}) {
  const opts = { ...parseArgs([]), ...options };
  const rows = loadDataRows();
  let rowIndex = 0;
  let tickCount = 0;

  console.log(`[Simulator] Starting simulator for ${opts.buildingId} (${ZONES.length} zones, interval: ${opts.intervalMs}ms)`);
  if (opts.anomalyZone) {
    console.log(`[Simulator] Injecting anomaly into zone: ${opts.anomalyZone}`);
  }

  const tick = async () => {
    const row = rows[rowIndex % rows.length];
    rowIndex++;
    tickCount++;

    const batch = generateBatch(row, opts);
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
  loadDataRows,
  generateBatch,
  sendBatch,
  runSimulator,
  parseArgs,
};

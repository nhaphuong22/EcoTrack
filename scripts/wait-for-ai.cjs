const path = require('path');
require('../backend/node_modules/dotenv').config({ path: path.resolve(__dirname, '../backend/.env') });

async function waitForAI({ url = process.env.AI_SERVICE_URL || 'http://127.0.0.1:8000',
  timeoutMs = 120000, intervalMs = 1000, fetchImpl = fetch,
  sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms)), now = Date.now } = {}) {
  const deadline = now() + timeoutMs;
  while (now() < deadline) {
    try {
      const response = await fetchImpl(`${url.replace(/\/$/, '')}/health`, {
        signal: AbortSignal.timeout(Math.min(2000, Math.max(1, deadline - now()))),
      });
      if (response.ok && (await response.json()).status === 'healthy') return;
    } catch { /* The reloader can bind its port before the app is ready. */ }
    await sleep(Math.min(intervalMs, Math.max(0, deadline - now())));
  }
  throw new Error(`AI did not become ready within ${timeoutMs / 1000}s. Check the AI process logs.`);
}

if (require.main === module) {
  console.log('[EcoTrack] Waiting for AI application startup...');
  waitForAI().then(() => console.log('[EcoTrack] AI ready; starting backend and frontend.'))
    .catch((error) => { console.error(`[EcoTrack] ${error.message}`); process.exitCode = 1; });
}
module.exports = { waitForAI };

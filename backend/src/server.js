require('dotenv').config();

if (!process.env.INTERNAL_API_KEY) {
  console.error('[EcoTrack Express Backend] ERROR: INTERNAL_API_KEY environment variable is required but not set.');
  process.exit(1);
}

const app = require('./app');
const { seedDefaultBuildingsIfNeeded } = require('./services/buildingService');

const PORT = process.env.PORT || 5000;

app.listen(PORT, async () => {
  console.log(`[EcoTrack Express Backend] Running on http://localhost:${PORT}`);
  console.log(`[EcoTrack Express Backend] Proxying AI requests to ${process.env.AI_SERVICE_URL || 'http://localhost:8000'}`);
  await seedDefaultBuildingsIfNeeded();
});

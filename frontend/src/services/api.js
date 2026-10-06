import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

/** GET /api/v1/energy/metrics */
export const fetchMetrics = () =>
  apiClient.get('/api/v1/energy/metrics').then(r => r.data);

/** GET /api/v1/energy/timeseries?limit=N */
export const fetchTimeSeries = (limit = 168) =>
  apiClient.get(`/api/v1/energy/timeseries?limit=${limit}`).then(r => r.data);

/** GET /api/v1/anomalies/events */
export const fetchAnomalies = () =>
  apiClient.get('/api/v1/anomalies/events').then(r => r.data);

/** GET /api/v1/forecast/predict */
export const fetchForecast = () =>
  apiClient.get('/api/v1/forecast/predict').then(r => r.data);

/** POST /api/v1/copilot/chat */
export const sendCopilotMessage = (
  message,
  buildingId = 'office_tower_01',
  history = [],
  anomalyId = null
) =>
  apiClient.post('/api/v1/copilot/chat', {
    message,
    building_id: buildingId,
    anomaly_id: anomalyId,
    history,
  }).then(r => r.data);

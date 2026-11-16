import axios from 'axios';

export const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000';

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
export const sendCopilotMessage = (message, buildingId = 'office_tower_01', history = []) =>
  apiClient.post('/api/v1/copilot/chat', {
    message,
    building_id: buildingId,
    history,
  }).then(r => r.data);

/** POST /api/v1/copilot/chat/stream */
export async function streamCopilotMessage({
  message,
  buildingId = 'office_tower_01',
  history = [],
  signal,
  onToken,
  onSources,
  onDone,
  onError,
}) {
  const url = `${API_BASE_URL}/api/v1/copilot/chat/stream`;
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      building_id: buildingId,
      history,
    }),
    signal,
  });

  if (!response.ok) {
    let errMessage = `HTTP ${response.status}`;
    try {
      const errJson = await response.json();
      errMessage = errJson.error || errMessage;
    } catch {}
    throw new Error(errMessage);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split('\n\n');
    buffer = events.pop();

    for (const evt of events) {
      if (!evt.trim()) continue;
      let eventType = 'message';
      let dataStr = '';

      for (const line of evt.split('\n')) {
        if (line.startsWith('event: ')) {
          eventType = line.slice(7).trim();
        } else if (line.startsWith('data: ')) {
          dataStr = line.slice(6);
        }
      }

      if (!dataStr) continue;
      try {
        const parsed = JSON.parse(dataStr);
        if (eventType === 'token') {
          if (parsed.token && onToken) onToken(parsed.token);
        } else if (eventType === 'sources') {
          if (onSources) onSources(parsed);
        } else if (eventType === 'done') {
          if (onDone) onDone(parsed);
        } else if (eventType === 'error') {
          if (onError) onError(parsed.error || 'Unknown error');
        }
      } catch (e) {
        console.warn('Failed to parse SSE JSON:', e);
      }
    }
  }
}

/** GET /api/v1/buildings/:id/zones */
export const fetchZones = (buildingId = 'office_tower_01') =>
  apiClient.get(`/api/v1/buildings/${buildingId}/zones`).then(r => r.data);

/** GET /health - Real system status inspection */
export const fetchSystemHealth = () =>
  apiClient.get('/health').then(r => r.data);


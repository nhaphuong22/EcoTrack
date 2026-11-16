import axios from 'axios';
import { getStoredAuth, refreshApi, clearAuthTokens } from './auth';

export const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

// Request Interceptor: Attach Bearer Access Token
apiClient.interceptors.request.use(
  (config) => {
    const { token } = getStoredAuth();
    if (token && !config.headers.Authorization) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response Interceptor: Silent Refresh on 401
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    if (error.response?.status === 401 && originalRequest && !originalRequest._retry) {
      originalRequest._retry = true;
      const { refreshToken } = getStoredAuth();

      if (refreshToken) {
        try {
          const newAuth = await refreshApi(refreshToken);
          originalRequest.headers.Authorization = `Bearer ${newAuth.token}`;
          return apiClient(originalRequest);
        } catch (refreshErr) {
          clearAuthTokens();
          if (typeof window !== 'undefined') {
            window.dispatchEvent(new Event('auth:logout'));
          }
          return Promise.reject(refreshErr);
        }
      } else {
        clearAuthTokens();
        if (typeof window !== 'undefined') {
          window.dispatchEvent(new Event('auth:logout'));
        }
      }
    }

    return Promise.reject(error);
  }
);

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

/** GET /api/v1/buildings/:id/zones */
export const fetchZones = (buildingId = 'office_tower_01') =>
  apiClient.get(`/api/v1/buildings/${buildingId}/zones`).then(r => r.data);

/** GET /health - Real system status inspection */
export const fetchSystemHealth = () =>
  apiClient.get('/health').then(r => r.data);

/** GET /api/v1/mlops/status */
export const fetchMLOpsStatus = () =>
  apiClient.get('/api/v1/mlops/status').then(r => r.data);

/** POST /api/v1/mlops/retrain */
export const triggerMLOpsRetrain = () =>
  apiClient.post('/api/v1/mlops/retrain').then(r => r.data);

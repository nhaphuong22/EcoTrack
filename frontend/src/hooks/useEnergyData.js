import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { API_BASE_URL, fetchMetrics, fetchTimeSeries, fetchAnomalies, fetchForecast } from '../services/api';

export function useEnergyData(timeSeriesLimit = 168) {
  const [metrics, setMetrics]       = useState(null);
  const [timeSeries, setTimeSeries] = useState([]);
  const [anomalies, setAnomalies]   = useState([]);
  const [forecast, setForecast] = useState([]);
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState(null);
  const retryTimer = useRef(null);
  const requestVersion = useRef(0);

  const load = useCallback(async (attempt = 0) => {
    clearTimeout(retryTimer.current);
    const version = ++requestVersion.current;
    setLoading(true);
    setError(null);
    try {
      const [m, ts, an, fc] = await Promise.all([
        fetchMetrics(),
        fetchTimeSeries(timeSeriesLimit),
        fetchAnomalies(),
        fetchForecast(),
      ]);
      if (version !== requestVersion.current) return;
      setMetrics(m);
      setTimeSeries(ts.data || []);
      setAnomalies(Array.isArray(an) ? an : []);
      setForecast(fc.forecast || []);
    } catch (err) {
      if (version !== requestVersion.current) return;
      setError(err?.message || 'Failed to fetch energy data');
      const status = err?.response?.status;
      if (attempt < 30 && (!status || [502, 503, 504].includes(status))) {
        retryTimer.current = setTimeout(() => load(attempt + 1), 2000);
      }
    } finally {
      if (version === requestVersion.current) setLoading(false);
    }
  }, [timeSeriesLimit]);

  useEffect(() => {
    load();
    let eventSource;
    if (typeof EventSource !== 'undefined' && API_BASE_URL) {
      eventSource = new EventSource(
        `${API_BASE_URL}/api/v1/stream/readings?building_id=office_tower_01`,
        { withCredentials: true }
      );
      eventSource.addEventListener('anomaly', (event) => {
        try {
          const incoming = JSON.parse(event.data);
          if (!incoming?.id) return;
          setAnomalies((prev) => [incoming, ...prev.filter((item) => item.id !== incoming.id)]);
        } catch {
          // Ignore malformed SSE anomaly payload
        }
      });
    }
    return () => {
      eventSource?.close();
      clearTimeout(retryTimer.current);
      requestVersion.current += 1;
    };
  }, [load]);

  const refetch = useCallback(() => load(), [load]);

  const syncedMetrics = useMemo(() => {
    if (!metrics) return null;
    if (metrics.source !== 'live_db' && anomalies.length === 0) return metrics;
    const active = anomalies.filter((a) => String(a?.status || 'OPEN').toUpperCase() !== 'IGNORED');
    const wasteVnd = active.reduce((sum, a) => sum + Number(a?.estimated_waste_vnd ?? 0), 0);
    const wasteUsd = active.reduce((sum, a) => sum + Number(a?.estimated_waste_usd ?? 0), 0);
    return {
      ...metrics,
      total_anomalies_detected: active.length,
      estimated_waste_cost_vnd: Math.round(wasteVnd),
      estimated_waste_cost_usd: Number(wasteUsd.toFixed(2)),
    };
  }, [metrics, anomalies]);

  return { metrics: syncedMetrics, timeSeries, anomalies, forecast, loading, error, refetch };
}

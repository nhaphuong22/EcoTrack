import { useState, useEffect, useCallback, useRef } from 'react';
import { fetchMetrics, fetchTimeSeries, fetchAnomalies, fetchForecast } from '../services/api';

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
    return () => {
      clearTimeout(retryTimer.current);
      requestVersion.current += 1;
    };
  }, [load]);

  const refetch = useCallback(() => load(), [load]);

  return { metrics, timeSeries, anomalies, forecast, loading, error, refetch };
}

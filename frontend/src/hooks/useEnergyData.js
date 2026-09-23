import { useState, useEffect, useCallback } from 'react';
import { fetchMetrics, fetchTimeSeries, fetchAnomalies } from '../services/api';

export function useEnergyData(timeSeriesLimit = 168) {
  const [metrics, setMetrics]       = useState(null);
  const [timeSeries, setTimeSeries] = useState([]);
  const [anomalies, setAnomalies]   = useState([]);
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [m, ts, an] = await Promise.all([
        fetchMetrics(),
        fetchTimeSeries(timeSeriesLimit),
        fetchAnomalies(),
      ]);
      setMetrics(m);
      setTimeSeries(ts.data || []);
      setAnomalies(Array.isArray(an) ? an : []);
    } catch (err) {
      setError(err?.message || 'Failed to fetch energy data');
    } finally {
      setLoading(false);
    }
  }, [timeSeriesLimit]);

  useEffect(() => { load(); }, [load]);

  return { metrics, timeSeries, anomalies, loading, error, refetch: load };
}

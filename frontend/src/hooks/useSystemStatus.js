import { useState, useEffect, useCallback } from 'react';
import { fetchSystemHealth } from '../services/api';

/**
 * Custom hook to poll and monitor real system health (Story 2.3, FR45).
 * Refreshes on initial mount and every 30 seconds thereafter.
 * Flags isUnknown = true whenever the health check is unreachable.
 */
export function useSystemStatus(pollIntervalMs = 30000) {
  const [healthData, setHealthData] = useState(null);
  const [isUnknown, setIsUnknown] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const loadHealth = useCallback(async () => {
    try {
      const data = await fetchSystemHealth();
      setHealthData(data);
      setIsUnknown(false);
      setError(null);
    } catch (err) {
      setIsUnknown(true);
      setError(err.message || 'Không thể kết nối đến máy chủ');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadHealth();

    const timer = setInterval(() => {
      loadHealth();
    }, pollIntervalMs);

    return () => clearInterval(timer);
  }, [loadHealth, pollIntervalMs]);

  return {
    healthData,
    isUnknown,
    loading,
    error,
    refetch: loadHealth,
  };
}

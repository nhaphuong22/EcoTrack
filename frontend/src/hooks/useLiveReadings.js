import { useState, useEffect, useRef, useCallback } from 'react';
import { API_BASE_URL } from '../services/api';

/**
 * Custom hook to stream real-time readings for building zones via SSE.
 * Manages live zone state updates, connection state, and backoff reconnection.
 */
export function useLiveReadings(buildingId = 'office_tower_01', initialZones = []) {
  const [zones, setZones] = useState(initialZones);
  const [isConnected, setIsConnected] = useState(false);
  const [retryAttempt, setRetryAttempt] = useState(0);

  const eventSourceRef = useRef(null);
  const reconnectTimerRef = useRef(null);

  // Sync zones whenever initialZones updates
  useEffect(() => {
    if (initialZones && initialZones.length > 0) {
      setZones(initialZones);
    }
  }, [initialZones]);

  const updateZoneWithReading = useCallback((reading) => {
    if (!reading || !reading.zone_id) return;

    setZones((prevZones) =>
      prevZones.map((z) => {
        if (z.id === reading.zone_id) {
          return {
            ...z,
            latest_reading: {
              timestamp: reading.timestamp || new Date().toISOString(),
              meter_reading_kwh: reading.meter_reading_kwh,
              outdoor_temperature_c: reading.outdoor_temperature_c,
              relative_humidity_pct: reading.relative_humidity_pct,
            },
          };
        }
        return z;
      })
    );
  }, []);

  const connect = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    const streamUrl = `${API_BASE_URL}/api/v1/stream/readings?building_id=${encodeURIComponent(buildingId)}`;
    
    // Check EventSource support
    if (typeof EventSource === 'undefined') {
      console.warn('[useLiveReadings] EventSource is not supported in this environment.');
      return;
    }

    const es = new EventSource(streamUrl);
    eventSourceRef.current = es;

    es.onopen = () => {
      setIsConnected(true);
      setRetryAttempt(0);
    };

    es.addEventListener('reading', (event) => {
      try {
        const reading = JSON.parse(event.data);
        updateZoneWithReading(reading);
      } catch (err) {
        console.error('[useLiveReadings] Error parsing reading event:', err);
      }
    });

    es.onerror = () => {
      setIsConnected(false);
      es.close();

      // Exponential backoff reconnect: 1s, 2s, 4s, 8s, up to 16s
      const delay = Math.min(1000 * Math.pow(2, retryAttempt), 16000);
      setRetryAttempt((prev) => prev + 1);

      reconnectTimerRef.current = setTimeout(() => {
        connect();
      }, delay);
    };
  }, [buildingId, retryAttempt, updateZoneWithReading]);

  useEffect(() => {
    connect();

    return () => {
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
      }
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, [buildingId]); // Reconnect if buildingId changes

  return {
    zones,
    isConnected,
    retryAttempt,
    setZones,
  };
}

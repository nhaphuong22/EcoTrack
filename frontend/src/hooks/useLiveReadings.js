import { useState, useEffect, useRef } from 'react';
import { API_BASE_URL } from '../services/api';

const EMPTY_ZONES = [];

export function useLiveReadings(buildingId = 'office_tower_01', initialZones = EMPTY_ZONES) {
  const [zones, setZones] = useState(initialZones);
  const [isConnected, setIsConnected] = useState(false);
  const [retryAttempt, setRetryAttempt] = useState(0);
  const buildingRef = useRef(buildingId);

  useEffect(() => {
    buildingRef.current = buildingId;
    setZones((previous) => initialZones.filter((z) => z.building_id === buildingId).map((zone) => {
      const current = previous.find((z) => z.id === zone.id && z.building_id === buildingId);
      return Date.parse(current?.latest_reading?.timestamp) > Date.parse(zone.latest_reading?.timestamp)
        ? { ...zone, latest_reading: current.latest_reading } : zone;
    }));
  }, [buildingId, initialZones]);

  useEffect(() => {
    let disposed = false;
    let eventSource;
    let timer;
    let failures = 0;
    setIsConnected(false);
    setRetryAttempt(0);

    function connect() {
      if (disposed || typeof EventSource === 'undefined') return;
      eventSource = new EventSource(
        `${API_BASE_URL}/api/v1/stream/readings?building_id=${encodeURIComponent(buildingId)}`,
        { withCredentials: true }
      );
      eventSource.onopen = () => {
        if (disposed) return;
        failures = 0;
        setIsConnected(true);
        setRetryAttempt(0);
      };
      eventSource.addEventListener('reading', (event) => {
        if (disposed || buildingRef.current !== buildingId) return;
        try {
          const reading = JSON.parse(event.data);
          const timestamp = Date.parse(reading.timestamp);
          if (reading.building_id !== buildingId || !reading.zone_id || !Number.isFinite(timestamp)) return;
          setZones((previous) => previous.map((zone) => {
            if (zone.id !== reading.zone_id || zone.building_id !== buildingId) return zone;
            const previousTimestamp = Date.parse(zone.latest_reading?.timestamp);
            if (Number.isFinite(previousTimestamp) && timestamp <= previousTimestamp) return zone;
            return { ...zone, latest_reading: {
              timestamp: reading.timestamp,
              meter_reading_kwh: reading.meter_reading_kwh,
              outdoor_temperature_c: reading.outdoor_temperature_c,
              relative_humidity_pct: reading.relative_humidity_pct,
            } };
          }));
        } catch (err) {
          console.error('[useLiveReadings] Invalid reading:', err);
        }
      });
      eventSource.onerror = () => {
        if (disposed) return;
        setIsConnected(false);
        eventSource.close();
        const delay = Math.min(1000 * 2 ** failures, 16000);
        failures += 1;
        setRetryAttempt(failures);
        timer = setTimeout(connect, delay);
      };
    }
    connect();
    return () => {
      disposed = true;
      clearTimeout(timer);
      eventSource?.close();
    };
  }, [buildingId]);

  return { zones, isConnected, retryAttempt, setZones };
}

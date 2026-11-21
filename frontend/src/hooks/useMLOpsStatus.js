import { useState, useEffect, useCallback, useRef } from 'react';
import { fetchMLOpsStatus, triggerMLOpsRetrain } from '../services/api';

const IDLE_MS = 30000;
const RETRAIN_MS = 4000;
const CEILING_MS = 15 * 60 * 1000;

const errorText = (err) =>
  err?.response?.data?.detail || err?.message || 'Không thể kết nối đến máy chủ';

/** Same rule as the gateway: ADMIN, or MANAGER of the building the dashboard shows. */
export const DASHBOARD_BUILDING = 'office_tower_01';
export const canViewMLOps = (user) =>
  user?.role === 'ADMIN' ||
  Boolean(user?.staff?.some((s) => s.role === 'MANAGER' && s.building_id === DASHBOARD_BUILDING));

/** Loads MLOps status; refreshes every 30 s, or every 4 s while a retrain runs; pauses while the tab is hidden. */
export function useMLOpsStatus() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [runId, setRunId] = useState(null);
  const [notice, setNotice] = useState(null);
  const [timedOut, setTimedOut] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const runRef = useRef({ id: null, since: 0, known: [] });
  const seqRef = useRef(0);
  const dataRef = useRef(null);

  const load = useCallback(async () => {
    const seq = ++seqRef.current;
    try {
      const next = await fetchMLOpsStatus();
      if (seq !== seqRef.current) return; // a newer request superseded this one
      dataRef.current = next;
      setData(next);
      setError(null);
      const { id, known } = runRef.current;
      // An unknown run_id (409 without a body id) is finished when any history row appears that was not there before.
      const finished = (h) => (id === 'unknown' ? !known.includes(h.run_id) : h.run_id === id);
      if (id && next?.retrain_history?.some(finished)) {
        runRef.current = { id: null, since: 0, known: [] };
        setRunId(null);
      }
    } catch (err) {
      if (seq === seqRef.current) setError(errorText(err)); // keep last data
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let timer;
    // Refresh first, so a run that finished is never reported as timed out.
    const tick = async () => {
      await load();
      const { id, since } = runRef.current;
      if (id && Date.now() - since >= CEILING_MS) {
        runRef.current = { id: null, since: 0, known: [] };
        setRunId(null);
        setTimedOut(true);
      }
    };
    const stop = () => {
      clearInterval(timer);
      timer = undefined;
    };
    const start = () => {
      stop();
      timer = setInterval(tick, runId ? RETRAIN_MS : IDLE_MS);
    };
    const onVisibility = () => {
      if (document.hidden) stop();
      else {
        tick();
        start();
      }
    };
    load(); // always load once, even when mounted in a hidden browser tab
    if (!document.hidden) start();
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      stop();
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [load, runId]);

  const track = (id, known) => {
    runRef.current = { id: id || 'unknown', since: Date.now(), known };
    setTimedOut(false);
    setRunId(runRef.current.id);
  };

  const retrain = useCallback(async () => {
    setNotice(null);
    setSubmitting(true);
    const known = (dataRef.current?.retrain_history || []).map((h) => h.run_id); // before the POST
    try {
      const res = await triggerMLOpsRetrain();
      track(res?.run_id, known);
      setNotice({ kind: 'info', text: 'Đã bắt đầu huấn luyện lại.' });
    } catch (err) {
      if (err?.response?.status === 409) {
        track(err.response.data?.run_id, known);
        setNotice({ kind: 'info', text: 'Đang có một lần huấn luyện lại đang chạy.' });
      } else {
        setNotice({ kind: 'error', text: errorText(err) });
      }
    } finally {
      setSubmitting(false);
    }
  }, []);

  return {
    data,
    loading,
    error,
    retraining: Boolean(runId) || submitting,
    timedOut,
    notice,
    retrain,
    refetch: load,
  };
}

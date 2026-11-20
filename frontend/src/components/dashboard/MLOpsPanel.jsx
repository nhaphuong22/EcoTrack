import { useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { Cpu, RefreshCw } from 'lucide-react';
import { useMLOpsStatus } from '../../hooks/useMLOpsStatus';

const BANNERS = {
  fallback: 'Mô hình champion chưa được xác định: đang dùng mô hình dự phòng (fallback).',
  unavailable: 'Mô hình champion không khả dụng (unavailable).',
  broken: 'Mô hình champion bị lỗi (broken).',
};
const fmt = (v, d = 3) => (typeof v === 'number' ? v.toFixed(d) : '—');
const axisTick = { fill: '#54655f', fontSize: 11 };

function Section({ title, error, empty, children }) {
  return (
    <section className="panel" aria-label={title}>
      <div className="panel-head">
        <h3 className="panel-title">{title}</h3>
      </div>
      <div className="p-4 text-sm">
        {error ? (
          <p role="alert" className="text-crit">
            Lỗi: {error}
          </p>
        ) : empty ? (
          <p className="text-muted">Chưa có dữ liệu.</p>
        ) : (
          children
        )}
      </div>
    </section>
  );
}

function BarsChart({ data, dataKey, unit, threshold, label }) {
  return (
    <div role="img" aria-label={label}>
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="#d2dbd8" strokeDasharray="2 4" vertical={false} />
          <XAxis dataKey="name" tick={axisTick} tickLine={false} axisLine={{ stroke: '#a9b8b3' }} />
          <YAxis tick={axisTick} tickLine={false} axisLine={false} unit={unit} width={48} />
          <Tooltip />
          {typeof threshold === 'number' && (
            <ReferenceLine y={threshold} stroke="#bd2630" strokeDasharray="3 3" />
          )}
          <Bar dataKey={dataKey} fill="#0c3a3e" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function MLOpsPanel({ isAdmin = false }) {
  const { data, loading, error, retraining, timedOut, notice, retrain, refetch } = useMLOpsStatus();
  const [confirming, setConfirming] = useState(false);

  if (loading && !data)
    return (
      <div className="panel p-6 text-sm text-muted" aria-busy="true">
        Đang tải trạng thái mô hình…
      </div>
    );
  if (!data)
    return (
      <p
        role="alert"
        className="rounded-md border border-crit/30 bg-crit-bg px-4 py-3 text-sm text-crit"
      >
        {error || 'Không có dữ liệu.'}
      </p>
    );

  const {
    champion,
    drift,
    anomaly_quality: aq,
    retrain_history: history,
    benchmark,
    errors: rawErrors,
  } = data;
  const errors = rawErrors || {};
  const status = champion?.status;
  const unhealthy = status && BANNERS[status];
  const signals = Object.entries(drift?.signals || {}).map(([name, s]) => ({
    name,
    psi: s?.psi,
  }));
  const models = benchmark?.models || [];

  const onRetrain = async () => {
    setConfirming(false);
    await retrain();
  };

  return (
    <div className="space-y-5" id="mlops-panel">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Cpu size={16} className="text-muted" aria-hidden="true" />
          <h2 className="text-base font-semibold text-ink">Giám sát mô hình (MLOps)</h2>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="btn btn-quiet btn-sm px-2"
            onClick={refetch}
            aria-label="Làm mới trạng thái mô hình"
          >
            <RefreshCw size={13} aria-hidden="true" />
          </button>
          {isAdmin &&
            (confirming ? (
              <>
                <span className="text-sm text-ink-2">Huấn luyện lại mô hình?</span>
                <button className="btn btn-primary btn-sm" onClick={onRetrain}>
                  Xác nhận
                </button>
                <button className="btn btn-quiet btn-sm" onClick={() => setConfirming(false)}>
                  Hủy
                </button>
              </>
            ) : (
              <button
                className="btn btn-primary btn-sm"
                disabled={retraining}
                onClick={() => setConfirming(true)}
              >
                {retraining ? 'Đang huấn luyện…' : 'Retrain'}
              </button>
            ))}
        </div>
      </div>

      {error && (
        <p role="alert" className="text-sm text-warn">
          Không làm mới được ({error}); đang hiển thị dữ liệu gần nhất.
        </p>
      )}
      {notice && (
        <p
          role="status"
          className={`text-sm ${notice.kind === 'error' ? 'text-crit' : 'text-ink-2'}`}
        >
          {notice.text}
        </p>
      )}
      {timedOut && (
        <p role="status" className="text-sm text-warn">
          Vẫn đang chạy hoặc chưa rõ: chưa thấy kết quả sau 15 phút.
        </p>
      )}

      {unhealthy && (
        <div
          role="alert"
          className="rounded-md border border-crit/30 bg-crit-bg px-4 py-3 text-sm text-crit"
        >
          <p>{BANNERS[status]}</p>
          {status === 'broken' && champion.error && (
            <p className="mt-1 text-base font-bold">{champion.error}</p>
          )}
        </div>
      )}

      <Section title="Champion" error={errors.champion} empty={!champion}>
        <p className="flex flex-wrap gap-x-6 gap-y-1">
          <span>
            Phiên bản: <b className="num">{champion?.version ?? '—'}</b>
          </span>
          <span>
            Huấn luyện: <b className="num">{champion?.trained_at ?? '—'}</b>
          </span>
          <span>
            Trạng thái: <b>{status ?? '—'}</b>
          </span>
        </p>
        {champion?.metrics && !unhealthy ? (
          <p className="mt-2 flex flex-wrap gap-x-6 text-ink-2">
            {Object.entries(champion.metrics).map(([k, v]) => (
              <span key={k}>
                {k}: <b className="num">{fmt(v)}</b>
              </span>
            ))}
          </p>
        ) : (
          <p className="mt-2 text-muted">Chưa có chỉ số.</p>
        )}
      </Section>

      <Section title="Drift" error={errors.drift} empty={!drift}>
        <p className={drift?.drift_detected ? 'font-semibold text-crit' : 'font-semibold text-ok'}>
          {drift?.drift_detected ? 'Phát hiện drift' : 'Không có drift'}
          {drift?.triggered_signals?.length > 0 && (
            <span className="font-normal"> · {drift.triggered_signals.join(', ')}</span>
          )}
        </p>
        <p className="meta mb-2">
          Kiểm tra lúc {drift?.checked_at ?? '—'} · MAPE {fmt(drift?.rolling_mape?.mape_percent, 2)}
          %
        </p>
        {signals.length > 0 && (
          <BarsChart
            data={signals}
            dataKey="psi"
            threshold={drift?.thresholds?.psi}
            label="PSI theo đặc trưng"
          />
        )}
      </Section>

      <Section title="Anomaly detector" error={errors.anomaly_quality} empty={!aq}>
        <p className="flex gap-6">
          <span>
            Precision: <b className="num">{fmt(aq?.precision)}</b>
          </span>
          <span>
            Recall: <b className="num">{fmt(aq?.recall)}</b>
          </span>
          <span>
            F1: <b className="num">{fmt(aq?.f1)}</b>
          </span>
        </p>
      </Section>

      <Section
        title="Lịch sử huấn luyện lại"
        error={errors.retrain_history}
        empty={!history?.length}
      >
        <table className="w-full text-left text-xs">
          <thead>
            <tr>
              <th>Run</th>
              <th>Thời gian</th>
              <th>Trigger</th>
              <th>Kết quả</th>
              <th>Champion</th>
              <th>Challenger</th>
              <th>Lý do</th>
            </tr>
          </thead>
          <tbody>
            {(history || []).map((h) => (
              <tr key={h.run_id}>
                <td className="num">{h.run_id}</td>
                <td className="num">{h.timestamp}</td>
                <td>{h.trigger}</td>
                <td>{h.outcome}</td>
                <td>{h.champion_version}</td>
                <td>{h.challenger_version}</td>
                <td>{h.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      <Section title="Benchmark" error={errors.benchmark} empty={!models.length}>
        <BarsChart
          data={models.map((m) => ({ name: m.model, mape: m.mape_percent }))}
          dataKey="mape"
          unit="%"
          label="MAPE theo mô hình"
        />
        <table className="mt-3 w-full text-left text-xs">
          <thead>
            <tr>
              <th>Mô hình</th>
              <th>MAE (kWh)</th>
              <th>RMSE (kWh)</th>
              <th>MAPE (%)</th>
              <th>R²</th>
            </tr>
          </thead>
          <tbody>
            {models.map((m) => (
              <tr key={m.model}>
                <td>{m.model}</td>
                <td className="num">{fmt(m.mae_kwh, 2)}</td>
                <td className="num">{fmt(m.rmse_kwh, 2)}</td>
                <td className="num">{fmt(m.mape_percent, 2)}</td>
                <td className="num">{fmt(m.r2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>
    </div>
  );
}

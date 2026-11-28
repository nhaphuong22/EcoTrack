import { useEffect, useRef, useState } from "react";
import { AlertCircle, FlaskConical, Loader2 } from "lucide-react";
import {
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { fetchWhatIf } from "../../services/api";

const number = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 1 });
const money = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 0 });

function RangeCard({ label, low, high, unit, fmt }) {
  return (
    <div className="rounded-md border border-line bg-white p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-muted">
        {label}
      </p>
      <p className="num mt-2 text-2xl font-semibold text-ink">
        {fmt.format(low)} – {fmt.format(high)} {unit}
      </p>
      <p className="mt-1 text-xs text-muted">
        Tiết kiệm 24 giờ tới (thấp – cao)
      </p>
    </div>
  );
}

export default function WhatIfPanel() {
  const [setpoint, setSetpoint] = useState(0);
  const [chillerOff, setChillerOff] = useState(0);
  const [sharePct, setSharePct] = useState("50");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const requestId = useRef(0);

  const share = Number(sharePct) / 100;
  const shareValid = sharePct !== "" && share >= 0.05 && share <= 0.8;

  useEffect(() => {
    const id = ++requestId.current;
    if (!shareValid) {
      // Stale numbers must not stay on screen for an input we refuse to simulate.
      setResult(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    const timer = setTimeout(() => {
      fetchWhatIf({
        setpoint_delta_c: setpoint,
        chiller_off_hours: chillerOff,
        hvac_share: share,
      })
        // Only the latest request may update the panel; slower earlier responses are dropped.
        .then((data) => id === requestId.current && setResult(data))
        .catch((err) => {
          if (id !== requestId.current) return;
          const detail = err?.response?.data?.detail;
          setResult(null);
          setError(
            typeof detail === "string"
              ? detail
              : Array.isArray(detail)
                ? detail.map((d) => d.msg).join("; ")
                : err.message || "Không thể mô phỏng.",
          );
        })
        .finally(() => id === requestId.current && setLoading(false));
    }, 300);
    return () => clearTimeout(timer);
  }, [setpoint, chillerOff, share, shareValid]);

  const chartData = (result?.hours || []).map((h) => ({
    label: `${String(h.vn_hour).padStart(2, "0")}:00`,
    baseline_kwh: h.baseline_kwh,
    scenario_range: [h.scenario_low_kwh, h.scenario_high_kwh],
  }));

  return (
    <section className="space-y-5" aria-labelledby="whatif-title">
      <div className="panel overflow-hidden">
        <div className="bg-shell px-5 py-5 text-white">
          <div className="mb-2 flex items-center gap-2 text-shell-muted">
            <FlaskConical size={16} aria-hidden="true" />
            <span className="text-xs font-semibold uppercase tracking-widest">
              What-if
            </span>
          </div>
          <h1 id="whatif-title" className="text-2xl font-semibold">
            Mô phỏng tiết kiệm HVAC
          </h1>
          <p className="mt-1 text-sm text-shell-muted">
            Ước tính trên dự báo 24 giờ tới khi nâng setpoint hoặc tắt chiller
            sớm.
          </p>
        </div>

        <div className="grid gap-5 p-5 md:grid-cols-3">
          <label className="text-sm font-medium text-ink">
            Nâng setpoint: <span className="num">+{setpoint} °C</span>
            <input
              type="range"
              min="0"
              max="2"
              step="0.5"
              value={setpoint}
              onChange={(e) => setSetpoint(Number(e.target.value))}
              className="mt-2 block w-full"
            />
          </label>
          <label className="text-sm font-medium text-ink">
            Tắt chiller sớm: <span className="num">{chillerOff} giờ</span>
            <input
              type="range"
              min="0"
              max="3"
              step="1"
              value={chillerOff}
              onChange={(e) => setChillerOff(Number(e.target.value))}
              className="mt-2 block w-full"
            />
          </label>
          <label className="text-sm font-medium text-ink">
            Tỷ trọng HVAC (%)
            <input
              type="number"
              min="5"
              max="80"
              step="5"
              value={sharePct}
              onChange={(e) => setSharePct(e.target.value)}
              aria-invalid={!shareValid}
              className="mt-1 block w-full rounded border border-line px-3 py-2 text-sm"
            />
            {!shareValid && (
              <span className="mt-1 block text-xs text-crit">
                Nhập từ 5 đến 80.
              </span>
            )}
          </label>
        </div>

        {error && (
          <div
            role="alert"
            className="mx-5 mb-5 flex items-center gap-2 rounded border border-crit/30 bg-crit-bg p-4 text-sm text-crit"
          >
            <AlertCircle size={18} aria-hidden="true" />
            {error}
          </div>
        )}
        {loading && !result && (
          <div className="flex min-h-40 items-center justify-center gap-3 text-muted">
            <Loader2 className="animate-spin" size={20} aria-hidden="true" />
            Đang mô phỏng...
          </div>
        )}

        {result && (
          <div className="space-y-5 px-5 pb-5" aria-busy={loading}>
            <div className="grid gap-3 sm:grid-cols-3">
              <RangeCard
                label="Điện năng"
                low={result.savings.low.kwh}
                high={result.savings.high.kwh}
                unit="kWh"
                fmt={number}
              />
              <RangeCard
                label="Chi phí"
                low={result.savings.low.vnd}
                high={result.savings.high.vnd}
                unit="₫"
                fmt={money}
              />
              <RangeCard
                label="CO₂"
                low={result.savings.low.co2_kg}
                high={result.savings.high.co2_kg}
                unit="kg"
                fmt={number}
              />
            </div>
            {result.notes?.map((note) => (
              <p key={note} className="text-sm text-warn">
                {note}
              </p>
            ))}

            <div className="rounded-md border border-line p-4">
              <h2 className="font-semibold">Dự báo gốc và kịch bản</h2>
              <p className="text-xs text-muted">
                kWh theo giờ (giờ Việt Nam) · Baseline{" "}
                {number.format(result.baseline.kwh)} kWh
              </p>
              <div className="mt-3 h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart
                    data={chartData}
                    margin={{ top: 6, right: 12, bottom: 0, left: 0 }}
                  >
                    <CartesianGrid
                      stroke="#dde6e3"
                      strokeDasharray="2 4"
                      vertical={false}
                    />
                    <XAxis
                      dataKey="label"
                      tick={{ fill: "#52635d", fontSize: 11 }}
                      tickLine={false}
                    />
                    <YAxis
                      tick={{ fill: "#52635d", fontSize: 11 }}
                      tickLine={false}
                      axisLine={false}
                    />
                    <Tooltip
                      formatter={(v) =>
                        Array.isArray(v)
                          ? `${number.format(v[0])} – ${number.format(v[1])} kWh`
                          : `${number.format(v)} kWh`
                      }
                    />
                    <Legend />
                    <Area
                      dataKey="scenario_range"
                      name="Kịch bản (thấp – cao)"
                      type="monotone"
                      stroke="none"
                      fill="#1f9d6b"
                      fillOpacity={0.25}
                    />
                    <Line
                      dataKey="baseline_kwh"
                      name="Baseline"
                      stroke="#1f55cc"
                      strokeWidth={1.75}
                      dot={false}
                    />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="rounded-md border border-line bg-sunken p-4">
              <h2 className="font-semibold">Giả định</h2>
              <ul className="mt-2 space-y-2 text-sm">
                {result.assumptions.map((a) => (
                  <li key={a.key}>
                    {a.label}{" "}
                    <span className="text-xs text-muted">
                      — Nguồn: {a.source}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

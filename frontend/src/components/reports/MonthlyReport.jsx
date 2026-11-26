import { useEffect, useMemo, useState } from 'react';
import { AlertCircle, BarChart3, Download, FileSpreadsheet, Loader2, TrendingDown, TrendingUp } from 'lucide-react';
import { fetchMonthlyReport } from '../../services/api';
import { exportMonthlyCsv, exportMonthlyPdf } from '../../lib/reportExport';

const number = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 1 });
const money = new Intl.NumberFormat('vi-VN');
const currentMonth = new Date().toISOString().slice(0, 7);

function Metric({ label, value, note }) {
  return (
    <div className="rounded-md border border-line bg-white p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-muted">{label}</p>
      <p className="num mt-2 text-2xl font-semibold text-ink">{value}</p>
      <p className="mt-1 text-xs text-muted">{note}</p>
    </div>
  );
}

export default function MonthlyReport() {
  const [month, setMonth] = useState(currentMonth);
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    fetchMonthlyReport(month)
      .then((data) => active && setReport(data))
      .catch((err) => active && setError(err?.response?.data?.detail || err.message || 'Không thể tạo báo cáo.'))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [month]);

  const maxDaily = useMemo(() => Math.max(...(report?.daily || []).map((day) => day.consumption_kwh), 1), [report]);
  const change = report?.summary.change_vs_previous_month_pct;

  return (
    <section className="space-y-5" aria-labelledby="report-title">
      <div className="panel overflow-hidden">
        <div className="flex flex-col gap-5 bg-shell px-5 py-5 text-white sm:flex-row sm:items-end sm:justify-between">
          <div>
            <div className="mb-2 flex items-center gap-2 text-shell-muted"><BarChart3 size={16} /><span className="text-xs font-semibold uppercase tracking-widest">Report Center</span></div>
            <h1 id="report-title" className="text-2xl font-semibold">Báo cáo năng lượng tháng</h1>
            <p className="mt-1 text-sm text-shell-muted">Tổng hợp hiệu suất vận hành, bất thường và dữ liệu kiểm chứng.</p>
          </div>
          <div className="flex flex-wrap items-end gap-2">
            <label className="text-xs font-medium text-shell-ink">Kỳ báo cáo
              <input type="month" max={currentMonth} value={month} onChange={(event) => setMonth(event.target.value)} className="mt-1 block rounded border border-shell-line bg-shell-2 px-3 py-2 text-sm text-white" />
            </label>
            <button className="btn btn-shell bg-shell" disabled={!report || loading} onClick={() => exportMonthlyCsv(report)}><FileSpreadsheet size={16} />CSV</button>
            <button className="btn bg-white text-shell hover:bg-sunken" disabled={!report || loading} onClick={() => exportMonthlyPdf(report)}><Download size={16} />Xuất PDF</button>
          </div>
        </div>

        {loading && <div className="flex min-h-64 items-center justify-center gap-3 text-muted"><Loader2 className="animate-spin" size={20} />Đang tổng hợp báo cáo...</div>}
        {error && <div role="alert" className="m-5 flex items-center gap-2 rounded border border-crit/30 bg-crit-bg p-4 text-sm text-crit"><AlertCircle size={18} />{error}</div>}
        {!loading && !error && report && (
          <div className="space-y-5 p-5">
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <Metric label="Tổng tiêu thụ" value={`${number.format(report.summary.total_consumption_kwh)} kWh`} note={`${report.summary.reading_count} bản ghi`} />
              <Metric label="Trung bình ngày" value={`${number.format(report.summary.average_daily_kwh)} kWh`} note={`${report.daily.length} ngày có dữ liệu`} />
              <Metric label="Công suất đỉnh" value={`${number.format(report.summary.peak_demand_kw)} kW`} note="Giá trị cao nhất trong kỳ" />
              <Metric label="Lãng phí ước tính" value={`${money.format(report.summary.estimated_waste_vnd)} ₫`} note={`${report.summary.anomaly_count} bất thường`} />
            </div>

            <div className="grid gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(260px,1fr)]">
              <div className="rounded-md border border-line p-4">
                <div className="mb-5 flex items-center justify-between"><div><h2 className="font-semibold">Tiêu thụ theo ngày</h2><p className="text-xs text-muted">kWh tổng hợp từ công tơ tòa nhà</p></div></div>
                {report.daily.length ? (
                  <div className="flex h-56 items-end gap-1.5 border-b border-line px-1" aria-label="Biểu đồ tiêu thụ theo ngày">
                    {report.daily.map((day) => <div key={day.date} className="group relative flex h-full min-w-0 flex-1 items-end" title={`${day.date}: ${number.format(day.consumption_kwh)} kWh`}><div className="w-full rounded-t-sm bg-ok transition-colors hover:bg-shell" style={{ height: `${Math.max(3, (day.consumption_kwh / maxDaily) * 100)}%` }} /></div>)}
                  </div>
                ) : <div className="flex h-56 items-center justify-center text-sm text-muted">Chưa có dữ liệu trong tháng này.</div>}
                <div className="mt-2 flex justify-between text-[11px] text-muted"><span>Đầu tháng</span><span>Cuối tháng</span></div>
              </div>

              <aside className="rounded-md border border-line bg-sunken p-4">
                <h2 className="font-semibold">Điểm nhấn vận hành</h2>
                <div className={`mt-4 flex items-start gap-3 rounded-md p-3 ${change != null && change <= 0 ? 'bg-ok-bg text-ok' : 'bg-warn-bg text-warn'}`}>
                  {change != null && change <= 0 ? <TrendingDown size={20} /> : <TrendingUp size={20} />}
                  <div><p className="font-semibold">{change == null ? 'Chưa đủ dữ liệu so sánh' : `${Math.abs(change)}% ${change <= 0 ? 'tiết kiệm hơn' : 'tăng so với'} tháng trước`}</p><p className="mt-1 text-xs opacity-80">So sánh tổng điện năng của hai kỳ liên tiếp.</p></div>
                </div>
                <dl className="mt-5 space-y-3 text-sm">
                  <div className="flex justify-between border-b border-line pb-2"><dt className="text-muted">Nghiêm trọng</dt><dd className="num font-semibold">{report.anomaly_breakdown.CRITICAL || 0}</dd></div>
                  <div className="flex justify-between border-b border-line pb-2"><dt className="text-muted">Cảnh báo</dt><dd className="num font-semibold">{report.anomaly_breakdown.WARNING || report.anomaly_breakdown.HIGH || 0}</dd></div>
                  <div className="flex justify-between"><dt className="text-muted">Tổng bất thường</dt><dd className="num font-semibold">{report.summary.anomaly_count}</dd></div>
                </dl>
              </aside>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

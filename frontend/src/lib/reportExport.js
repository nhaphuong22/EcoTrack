const money = new Intl.NumberFormat('vi-VN');
const number = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 1 });

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function exportMonthlyCsv(report) {
  const headers = ['Ngày', 'Điện năng (kWh)', 'Công suất đỉnh (kW)', 'Số bản ghi'];
  const rows = report.daily.map((day) => [day.date, day.consumption_kwh, day.peak_demand_kw, day.readings]);
  const csv = [headers, ...rows]
    .map((row) => row.map((cell) => `"${String(cell).replaceAll('"', '""')}"`).join(','))
    .join('\r\n');
  downloadBlob(new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8' }), `ecotrack-${report.month}.csv`);
}

function line(ctx, label, value, x, y) {
  ctx.fillStyle = '#54655f';
  ctx.font = '24px "Segoe UI", sans-serif';
  ctx.fillText(label, x, y);
  ctx.fillStyle = '#0e1e1d';
  ctx.font = 'bold 38px "Segoe UI", sans-serif';
  ctx.fillText(value, x, y + 48);
}

export async function exportMonthlyPdf(report) {
  const { jsPDF } = await import('jspdf');
  const canvas = document.createElement('canvas');
  canvas.width = 1240;
  canvas.height = 1754;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#fafcfb';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = '#0c3a3e';
  ctx.fillRect(0, 0, canvas.width, 210);
  ctx.fillStyle = '#ffffff';
  ctx.font = 'bold 52px "Segoe UI", sans-serif';
  ctx.fillText('ECOTRACK', 72, 86);
  ctx.font = '30px "Segoe UI", sans-serif';
  ctx.fillText(`Báo cáo năng lượng tháng ${report.month}`, 72, 145);
  ctx.font = '22px "Segoe UI", sans-serif';
  ctx.fillText(report.building.name, 72, 184);

  line(ctx, 'Tổng tiêu thụ', `${number.format(report.summary.total_consumption_kwh)} kWh`, 72, 285);
  line(ctx, 'Trung bình ngày', `${number.format(report.summary.average_daily_kwh)} kWh`, 650, 285);
  line(ctx, 'Công suất đỉnh', `${number.format(report.summary.peak_demand_kw)} kW`, 72, 430);
  line(ctx, 'Chi phí lãng phí ước tính', `${money.format(report.summary.estimated_waste_vnd)} ₫`, 650, 430);

  ctx.fillStyle = '#0e1e1d';
  ctx.font = 'bold 30px "Segoe UI", sans-serif';
  ctx.fillText('Tiêu thụ điện theo ngày', 72, 590);
  const chart = { x: 72, y: 640, width: 1096, height: 340 };
  ctx.strokeStyle = '#d2dbd8';
  ctx.strokeRect(chart.x, chart.y, chart.width, chart.height);
  const max = Math.max(...report.daily.map((item) => item.consumption_kwh), 1);
  const gap = 6;
  const barWidth = Math.max(8, chart.width / Math.max(report.daily.length, 1) - gap);
  report.daily.forEach((day, index) => {
    const height = (day.consumption_kwh / max) * (chart.height - 50);
    ctx.fillStyle = '#17784a';
    ctx.fillRect(chart.x + index * (barWidth + gap) + 8, chart.y + chart.height - height - 30, barWidth, height);
  });
  ctx.fillStyle = '#54655f';
  ctx.font = '20px "Segoe UI", sans-serif';
  ctx.fillText(`Cao nhất: ${number.format(max)} kWh/ngày`, 72, 1025);

  ctx.fillStyle = '#0e1e1d';
  ctx.font = 'bold 30px "Segoe UI", sans-serif';
  ctx.fillText('Tóm tắt vận hành', 72, 1120);
  ctx.font = '24px "Segoe UI", sans-serif';
  const change = report.summary.change_vs_previous_month_pct;
  const statements = [
    `• ${report.summary.anomaly_count} bất thường được ghi nhận trong tháng.`,
    `• Mức tiêu thụ ${change == null ? 'chưa đủ dữ liệu để so sánh' : `${Math.abs(change)}% ${change <= 0 ? 'thấp hơn' : 'cao hơn'} tháng trước`}.`,
    `• Báo cáo gồm ${report.summary.reading_count} bản ghi từ hệ thống đo đếm.`,
  ];
  statements.forEach((statement, index) => ctx.fillText(statement, 90, 1180 + index * 54));

  ctx.fillStyle = '#7c8b87';
  ctx.font = '20px "Segoe UI", sans-serif';
  ctx.fillText(`Tạo lúc ${new Date(report.generated_at).toLocaleString('vi-VN')} • ${report.report_id}`, 72, 1660);
  const pdf = new jsPDF({ unit: 'mm', format: 'a4', orientation: 'portrait' });
  pdf.addImage(canvas.toDataURL('image/jpeg', 0.92), 'JPEG', 0, 0, 210, 297);
  pdf.save(`ecotrack-${report.month}.pdf`);
}

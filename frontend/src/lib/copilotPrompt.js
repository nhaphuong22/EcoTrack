export function buildAnomalyPrompt(anomaly) {
  const anom = anomaly || {};
  const id = anom.id || 'N/A';
  const time = anom.timestamp ? String(anom.timestamp).slice(0, 16) : 'N/A';
  const delta = Number.isFinite(anom.delta_kwh)
    ? (anom.delta_kwh >= 0 ? `+${anom.delta_kwh}` : `${anom.delta_kwh}`)
    : '+0';
  const score = Number.isFinite(anom.anomaly_score)
    ? anom.anomaly_score.toFixed(2)
    : 'N/A';

  return (
    `Phân tích sự cố ${id} xảy ra lúc ${time} — ` +
    `phụ tải tăng ${delta} kWh so với baseline, điểm bất thường ${score}. ` +
    `Chẩn đoán nguyên nhân và đề xuất hành động xử lý.`
  );
}

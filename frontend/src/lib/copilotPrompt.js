export function buildAnomalyPrompt(anomaly) {
  const anom = anomaly || {};
  const id = anom.id || 'N/A';
  const time = anom.timestamp ? String(anom.timestamp).slice(0, 16) : 'N/A';
  const delta = anom.delta_kwh != null ? `+${anom.delta_kwh}` : '+0';
  const score = typeof anom.anomaly_score === 'number'
    ? anom.anomaly_score.toFixed(2)
    : (anom.anomaly_score ?? 'N/A');

  return (
    `Phân tích sự cố ${id} xảy ra lúc ${time} — ` +
    `phụ tải tăng ${delta} kWh so với baseline, điểm bất thường ${score}. ` +
    `Chẩn đoán nguyên nhân và đề xuất hành động xử lý.`
  );
}

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

export function buildZonePrompt(zone) {
  const z = zone || {};
  const name = z.name || z.id || 'Khu vực';
  const r = z.latest_reading || {};
  const temp = Number.isFinite(r.outdoor_temperature_c) ? `${r.outdoor_temperature_c}°C` : 'N/A';
  const kwh = Number.isFinite(r.meter_reading_kwh) ? `${r.meter_reading_kwh} kWh` : 'N/A';
  const hum = Number.isFinite(r.relative_humidity_pct) ? `${r.relative_humidity_pct}%` : 'N/A';

  return (
    `Phân tích tình trạng tiêu thụ năng lượng và vi khí hậu tại ${name} (${z.id || 'N/A'}). ` +
    `Thông số hiện tại: công suất tiêu thụ ${kwh}, nhiệt độ phòng ${temp}, độ ẩm ${hum}. ` +
    `Đưa ra đánh giá về hiệu quả năng lượng và các khuyến nghị tối ưu vận hành.`
  );
}


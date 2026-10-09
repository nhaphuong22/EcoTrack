import { describe, it, expect } from 'vitest';
import { buildAnomalyPrompt } from '../copilotPrompt';

describe('buildAnomalyPrompt', () => {
  it('builds a diagnostic prompt for a complete anomaly', () => {
    const anomaly = {
      id: 'ANOM-1234',
      timestamp: '2026-10-09T14:30:00Z',
      delta_kwh: 45.5,
      anomaly_score: 0.8765,
    };

    const prompt = buildAnomalyPrompt(anomaly);
    expect(prompt).toContain('ANOM-1234');
    expect(prompt).toContain('2026-10-09T14:30');
    expect(prompt).toContain('+45.5 kWh');
    expect(prompt).toContain('0.88');
    expect(prompt).toContain('Chẩn đoán nguyên nhân và đề xuất hành động xử lý');
  });

  it('handles sparse/missing fields defensively without NaN or undefined', () => {
    const emptyPrompt = buildAnomalyPrompt({});
    expect(emptyPrompt).not.toContain('undefined');
    expect(emptyPrompt).not.toContain('NaN');
    expect(emptyPrompt).toContain('N/A');
    expect(emptyPrompt).toContain('+0 kWh');

    const nullPrompt = buildAnomalyPrompt(null);
    expect(nullPrompt).not.toContain('undefined');
    expect(nullPrompt).not.toContain('NaN');
  });
});

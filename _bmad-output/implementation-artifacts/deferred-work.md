# Deferred Work

## Deferred from: code review of spec-1-1-serve-energy-metrics-and-time-series-from-bdg2-data (2026-10-08)

- `/metrics` and `/anomalies` are computed over different frames (medium). `/internal/energy/metrics` and the `query_metrics` copilot tool now read the 720h replayed real-data serving frame, while `/internal/anomalies/detect`, `get_anomalies` and `query_forecast_summary` still use the old synthetic `data_loader` → `predict_horizon` → `detect_anomalies` pipeline. The dashboard's `total_anomalies_detected` metric will not match the anomaly list. The spec's "Temporary mix" design note accepts this during the interim and forbids changing `anomalies.py` beyond the tariff constant. Resolve in Story 1.3 when the anomaly endpoint moves onto the unified pipeline.
- Heuristic RCA cost line is untested (low). `ai-service/src/agent/orchestrator.py:142` interpolates `delta_kwh * get_tariff_rate_vnd()` / `* get_tariff_rate_usd()` into user-visible heuristic chat text with no test covering `_generate_heuristic_response`. Demo-template text rather than a contract; add coverage when the Copilot RCA path gets its own tests (Epic 4).

## Deferred from: code review of spec-1-4-forecast-the-next-24-hours (2026-10-09)

- Malformed / partial `model_metadata.json` raises an unhandled `KeyError` → bare 500 with no error envelope (low, pre-existing). `ai-service/src/data_pipeline/serving_frame.py:91` reads `metadata["xgboost_metrics"]["rmse_kwh"]` in `_load_artifacts_and_base_frame` (runs inside `get_serving_frame`, before `predict_next_24h`); a present-but-incomplete metadata file escapes the `ModelArtifactError` path and surfaces as an un-enveloped 500. Pre-existing Story 1.1 loader behavior, not introduced by Story 1.4; the I/O matrix covers only a wholly-absent artifact. Add a validation/guard (and a present-but-incomplete-metadata matrix row + test) when the serving-frame loader is next revisited.

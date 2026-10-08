# Epic 1 Context: Trustworthy Real-Data Foundation

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Make every number the operator sees come from the real BDG2-trained models and data, and make failures visible instead of silently masked. Today `ai-service` holds two disconnected ML stacks: the API serves a model fitted in-sample on a small synthetic dataset, while the real-data training pipeline and its artifacts are used only by tests. This epic joins them and fixes the foundation defects (silent fallbacks, unchecked internal token, duplicate readings, a dropped Copilot prompt) that every later epic would otherwise build on. It is shared by the whole team and must finish before the other epics branch off.

## Stories

- Story 1.1: Serve energy metrics and time series from BDG2 data
- Story 1.2: Forecast the next 24 hours
- Story 1.3: Detect anomalies on the unified pipeline and fail loudly
- Story 1.4: Make Copilot provider failures visible
- Story 1.5: Enforce the internal service token
- Story 1.6: Store each meter reading once
- Story 1.7: Open the Copilot with the anomaly's context

## Requirements & Constraints

- Energy metrics, time series, forecasts and anomalies must be produced from the BDG2-trained artifacts and the real-data feature pipeline; the synthetic in-sample serving path must end up unused and removed.
- The forecast must cover the 24 hours after the last observed reading, with 95% bounds, and answer within 300 ms at the 95th percentile.
- A missing model artifact is an explicit error to the caller. Training a placeholder model and saving it over the real artifact path is not acceptable.
- LLM provider failures must be logged, and model names must come from configuration.
- The AI service must refuse internal routes without the shared internal token, and no default secret may ship in code.
- A building has at most one meter reading per timestamp.
- The anomaly "Ask Copilot" action must deliver its prepared prompt to the chat.
- Existing response field names and shapes must not change: the gateway and the frontend consume them as they are today.
- Timestamps crossing an API boundary are ISO 8601 UTC; energy values are floats in kWh or kW.
- Real BDG2 data files and model artifacts are not in version control, so tests must pass in CI without them.
- Every story ships tests for its own scope, and CI stays green.

## Technical Decisions

- The system is an Express gateway (Prisma, PostgreSQL) in front of a FastAPI AI service. The architecture document predates this split: paths it places under `backend/src/{models,agent,data_pipeline}` now live under `ai-service/src/`.
- ML and data-pipeline modules stay plain Python, importable and callable without FastAPI.
- CPU-bound work inside FastAPI handlers runs through `asyncio.to_thread`.
- Errors use the envelope `{"detail": ..., "code": ...}` with a matching HTTP status.
- Configuration comes from environment variables; nothing sensitive is hardcoded.
- The AI service has no database driver; it reads its data from files. The gateway owns PostgreSQL.
- Reuse the existing real-data inference helper and training script rather than writing new feature code.

## UX & Interaction Patterns

- The dashboard, its chart and the Copilot drawer keep their current look and behaviour; this epic changes where the data comes from, not how it is shown.
- Clicking "Copilot" on an anomaly opens the drawer and sends that anomaly's diagnostic prompt as the first message.

## Cross-Story Dependencies

- Story 1.1 establishes the shared real-data source that Stories 1.2 and 1.3 build on; removal of the old synthetic serving path completes in Story 1.3.
- Stories 1.4 to 1.7 are independent of each other and of 1.1 to 1.3.
- Story 1.6 adds a uniqueness rule that Epic 5 later extends when readings gain a zone.
- Epics 2 to 6 all assume this epic is complete.

---
title: 'Story 2.3: Show real system status'
type: 'feature'
created: '2026-10-22'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
story_keys:
  - 2-3-show-real-system-status
context:
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The dashboard currently displays hardcoded mock system status indicators (e.g. static "Đang chạy" / "Sẵn sàng" text) in the UI. Facility operators cannot determine whether the database, the AI FastAPI microservice, the Machine Learning models (XGBoost, Isolation Forest), or the AI Copilot reasoning engine are genuinely healthy, offline, or degraded. FR45 requires a real-time `/health` check in the gateway and a dynamic status board that polls every 30 seconds with graceful fallback to "unknown".

**Approach (Ponytail - lean, zero boilerplate, 100% real):**
- Update FastAPI `ai-service` `/health` to verify model artifacts existence (`xgboost_forecaster.joblib`, `isolation_forest.joblib`) and identify active Copilot engine (`google_genai`, `openai`, `rule_based_fallback`).
- Enhance Express Gateway `GET /health` to:
  - Check database reachability via `prisma.$queryRaw` with timeout protection.
  - Check AI microservice health via `callAIService('/health')`.
  - Assemble comprehensive health status payload with database, AI service, model states, and copilot engine.
- Create a dedicated frontend component `SystemStatus.jsx` and hook `useSystemStatus.js` (or integrate into `App.jsx`):
  - Fetches from `GET /health` on initial mount.
  - Sets up an interval to refresh every 30 seconds.
  - Dynamically computes each component's status without hardcoded values.
  - When the endpoint cannot be reached, displays every component as "unknown" ("Không xác định" / amber badge).

## Boundaries & Constraints

**Always:**
- Gateway `GET /health` returns JSON with database, AI service, model loading states, and copilot engine.
- Polling in frontend happens every 30,000 ms (30s) and is cleaned up on unmount.
- When `/health` cannot be reached or throws, all components show as "unknown".
- Test coverage covers:
  - Backend `GET /health` (healthy, db down, ai-service down).
  - Frontend status panel (healthy render, model down render, network failure "unknown" fallback, 30s timer).

**Never:**
- Do not keep hardcoded statuses in UI.
- Do not let a slow database or AI service health check hang indefinitely; use strict timeouts (e.g. 2-3s).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| All Healthy | DB up, AI up, models exist | `GET /health` 200: all components "healthy" / "loaded" | Normal render |
| AI Service Down | AI service offline / connection refused | Gateway reports `ai_service: "unavailable"`, `models: { forecast: "unavailable", anomaly: "unavailable" }`, `copilot_engine: "unavailable"` | HTTP 200 (or 503 degraded), AI components shown as unavailable |
| DB Disconnected | DB connection fails / timeout | Gateway reports `database: "disconnected"` | Handled cleanly in try/catch |
| Gateway Down | Browser cannot reach `/health` | Frontend catches error and marks every component as "unknown" | Amber "Không xác định" state |

</frozen-after-approval>

## Code Map

- `ai-service/src/main.py`: Enhance `/health` to inspect model files and copilot engine.
- `backend/src/routes/health.js` (NEW) or `backend/src/app.js`: Implement robust `/health` checker inspecting Prisma DB & AI microservice.
- `backend/tests/health.test.js`: Update tests covering multi-service health inspection.
- `frontend/src/services/api.js`: Add `fetchSystemHealth()`.
- `frontend/src/hooks/useSystemStatus.js` (NEW): Custom hook polling `/health` every 30s with error handling.
- `frontend/src/components/dashboard/SystemStatus.jsx` (NEW): Status widget displaying live component badges.
- `frontend/src/App.jsx`: Replace hardcoded status markup with `<SystemStatus />`.
- `frontend/src/__tests__/SystemStatus.test.jsx` (NEW): Complete tests for healthy, unavailable, and unknown states.

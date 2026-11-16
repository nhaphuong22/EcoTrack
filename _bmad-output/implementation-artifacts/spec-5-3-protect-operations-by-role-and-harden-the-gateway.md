---
title: 'Story 5.3: Protect operations by role and harden the gateway'
type: 'feature'
created: '2026-11-16'
status: 'done'
story_keys:
  - 5-3-protect-operations-by-role-and-harden-the-gateway
context:
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-EcoTrack-2026-09-23/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-5-1-sign-in-with-a-role.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-5-2-stay-signed-in-and-sign-out.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Domain endpoints across `/api/v1/*` (buildings, energy metrics, forecasting, anomaly lifecycle, Copilot streaming, readings stream, MLOps) are currently open or protected solely by service-to-service internal keys. Unauthenticated users or lower-privileged roles (such as Technicians) can perform high-impact admin operations like adding buildings, clearing cache, or retraining AI models. Additionally, the Express gateway lacks HTTP security headers (Helmet), uses open CORS, and `/auth/*` endpoints lack brute-force rate-limiting.

**Approach:**
1. Implement `requireRole(...roles)` middleware that checks `req.user.role` and responds with HTTP 403 `{"error": "Forbidden: Insufficient permissions"}` if the user lacks an authorized role.
2. Apply the comprehensive Role Matrix across the gateway:
   - `ADMIN` only: `POST /api/v1/buildings`, `POST /api/v1/energy/cache/clear`, `POST /api/v1/mlops/retrain`.
   - `ADMIN` & `MANAGER`: `GET /api/v1/mlops/status`.
   - `ADMIN`, `MANAGER`, `TECHNICIAN`: `PATCH /api/v1/anomalies/:id/status`, plus read-only domain queries.
   - Authentication required (`requireAuth`): All remaining `/api/v1/*` domain routes (buildings list/detail, energy metrics/series, forecast, anomalies, Copilot chat, live stream).
   - Exempt / Open endpoints: `/health`, `/api/v1/health`, `GET /`, `/api/v1/auth/*` (login, refresh, logout), and `POST /api/v1/ingest/readings` (guarded by `X-Ingest-Key` for automated sensors).
3. Harden the Express gateway in `src/app.js`:
   - Enable `helmet` for defense-in-depth security headers.
   - Configure CORS using `CORS_ORIGINS` (comma-separated list, defaulting to `http://localhost:3000,http://localhost:5173`).
   - Rate limit `/api/v1/auth/*` to prevent brute force, returning HTTP 429 when threshold is breached.
4. Provide a shared authentication helper for test suites so existing tests continue passing without regression.

## Boundaries & Constraints

**Always:**
- Apply Ponytail Ladder: Simple, composable functional middleware (`requireRole(...roles)`). Avoid complex policy engine frameworks or permission DSLs.
- Protected routes without valid authentication must return HTTP 401 `{"error": "Authentication token required"}` or `{"error": "Invalid or expired token"}`.
- Authenticated requests with mismatched roles must return HTTP 403 `{"error": "Forbidden: Insufficient permissions"}`.
- Health check endpoints (`/health`, `/api/v1/health`, `GET /`) must remain completely unauthenticated for orchestrator probes.
- Ingest endpoint (`POST /api/v1/ingest/readings`) must remain accessible with `X-Ingest-Key` alone to support standalone IoT sensors and simulator bots.
- Rate-limiting applies to `/api/v1/auth/*` (login, refresh, logout) and returns HTTP 429 with `{ error: 'Too many requests, please try again later.' }`.
- In test environments, disable or set high rate limits to ensure automated test runs are never throttled.

**Never:**
- Never hardcode wildcard `*` for CORS when `CORS_ORIGINS` is configured.
- Never allow a `TECHNICIAN` or `MANAGER` to trigger `POST /buildings`, `POST /energy/cache/clear`, or `POST /mlops/retrain`.
- Never allow unauthenticated access to domain data (energy telemetry, anomaly reports, copilot chats).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Missing Auth on Protected Route | `GET /api/v1/buildings` without Bearer token | HTTP 401 `{"error": "Authentication token required"}` | Block access |
| Technician calls Admin Route | `POST /api/v1/buildings` with `TECHNICIAN` role token | HTTP 403 `{"error": "Forbidden: Insufficient permissions"}` | Block access |
| Technician calls Cache Clear | `POST /api/v1/energy/cache/clear` with `TECHNICIAN` role | HTTP 403 `{"error": "Forbidden: Insufficient permissions"}` | Block access |
| Technician calls MLOps Retrain | `POST /api/v1/mlops/retrain` with `TECHNICIAN` role | HTTP 403 `{"error": "Forbidden: Insufficient permissions"}` | Block access |
| Manager calls MLOps Status | `GET /api/v1/mlops/status` with `MANAGER` role | HTTP 200 (serves status data) | Allowed |
| Manager calls MLOps Retrain | `POST /api/v1/mlops/retrain` with `MANAGER` role | HTTP 403 `{"error": "Forbidden: Insufficient permissions"}` | Block access |
| Admin calls any Protected Route | Any route with `ADMIN` role token | HTTP 200/201 (success) | Allowed |
| Any Role updates Anomaly Status | `PATCH /api/v1/anomalies/:id/status` with valid token | HTTP 200 | Allowed for all 3 roles |
| Sensor Ingest with API Key | `POST /api/v1/ingest/readings` with `X-Ingest-Key` | HTTP 201 (persists readings) | No Bearer token required |
| Health Check Probe | `GET /health` with no headers | HTTP 200 `{"status": "ok", ...}` | Always open |
| Brute Force Auth Requests | Exceeding rate limit on `POST /api/v1/auth/login` | HTTP 429 `{"error": "Too many requests, please try again later."}` | Throttle requests |
| Security Headers Check | Any HTTP response | Headers include `X-Content-Type-Options: nosniff`, HSTS, etc. | Set by Helmet |

</frozen-after-approval>

## Code Map

- `backend/package.json` — Add `helmet` and `express-rate-limit`.
- `backend/src/middleware/requireRole.js` (new) — Export `requireRole(...roles)` checking `req.user.role`.
- `backend/src/routes/mlops.js` (new) — Mount `GET /api/v1/mlops/status` (`requireRole('ADMIN', 'MANAGER')`) and `POST /api/v1/mlops/retrain` (`requireRole('ADMIN')`).
- `backend/src/routes/buildings.js` — Apply `requireRole('ADMIN')` on `POST /`.
- `backend/src/routes/energy.js` — Apply `requireRole('ADMIN')` on `POST /cache/clear`.
- `backend/src/routes/anomalies.js` — Ensure `PATCH /:id/status` permits all roles (`requireRole('ADMIN', 'MANAGER', 'TECHNICIAN')`).
- `backend/src/app.js`:
  - Integrate `helmet()`.
  - Configure `cors()` with origin list from `process.env.CORS_ORIGINS`.
  - Set up `express-rate-limit` on `/api/v1/auth/*`.
  - Apply `requireAuth` to all domain routers (`buildings`, `energy`, `forecast`, `anomalies`, `copilot`, `stream`, `mlops`).
- `backend/tests/setup.js` — Provide helper functions:
  - `generateTestToken(role)`: Helper generating valid JWT tokens for tests.
  - `authHeaderFor(role)`: Returns `{ Authorization: 'Bearer ...' }`.
- `backend/tests/rbac.test.js` (new) — Dedicated suite testing:
  - 401 unauthenticated on protected routes.
  - 403 on role violations across the matrix.
  - Rate limiting behavior (429).
  - Helmet security headers and CORS behavior.
- Existing test suites (`buildings.test.js`, `proxy.test.js`, `zones.test.js`, `anomalies.test.js`, etc.) — update request calls to include authorization headers so the entire suite passes cleanly.

## Tasks & Acceptance

**Execution:**
- [x] Add `helmet` and `express-rate-limit` to `backend/package.json` and install.
- [x] Implement `requireRole(...roles)` middleware in `backend/src/middleware/requireRole.js` — FR35.
- [x] Create `backend/src/routes/mlops.js` with proxy/mock endpoints guarded by `requireRole` — FR40.
- [x] Apply role protections on `POST /buildings` and `POST /energy/cache/clear` (`ADMIN`) and `PATCH /anomalies/:id/status` — FR35.
- [x] Configure `helmet`, strict CORS, and `/api/v1/auth/*` rate-limiting in `backend/src/app.js` — NFR2.
- [x] Apply `requireAuth` across domain routers in `backend/src/app.js` (keeping `/health`, `GET /`, and ingest open) — FR35.
- [x] Add `generateTestToken` in `backend/tests/setup.js` and verify/update existing tests to pass.
- [x] Create `backend/tests/rbac.test.js` to verify role matrix, security headers, CORS, and rate limiting.

**Acceptance Criteria:**
- Given a `requireRole(...roles)` middleware,
- When an authenticated user without an allowed role calls a protected endpoint,
- Then the response is 403.
- Given the role matrix,
- When it is applied,
- Then `POST /buildings`, `POST /energy/cache/clear` and `POST /api/v1/mlops/retrain` require `ADMIN`; `GET /api/v1/mlops/status` requires `ADMIN` or `MANAGER`; `PATCH /anomalies/:id/status` allows all three roles; the ingest and readings-stream routes plus all other `/api/v1/*` routes require authentication; `/health`, `/api/v1/auth/login` and the `X-Ingest-Key`-guarded ingest endpoint stay reachable as defined.
- Given the gateway,
- When it starts,
- Then `helmet` is enabled, CORS allows only origins listed in `CORS_ORIGINS`, and `/api/v1/auth/*` is rate-limited to a configurable number of requests per minute, returning 429 beyond it.
- Given the existing test suite,
- When it runs,
- Then tests authenticate through a shared helper and all pass.

## Design Notes

- **Ponytail Ladder:** Role checking is a straightforward array lookup `roles.includes(req.user.role)` inside a higher-order middleware function. No bloated RBAC permission hierarchies, AST policy engines, or casbin rules are introduced.
- **Ingest Separation:** Machine-to-machine sensor ingest deliberately stays decoupled from human user JWTs, maintaining resilience for IoT edge devices using `X-Ingest-Key`.

## Review Triage Log

- 2026-11-16: Code Review completed via `/bmad-code-review` and `/ponytail-review`.
  - [BMAD Criteria]: 100% AC achieved. `requireRole` middleware returns 403 on role mismatch, role matrix applied across all routes (`ADMIN` on buildings/cache/retrain, `ADMIN`/`MANAGER` on MLOps status, all 3 roles on anomalies status), open routes remain open, Helmet security headers verified, CORS configured, and auth rate-limiting enforced.
  - [Ponytail Review]: Score 🟢 **Lean**. Clean composable Express middleware without unnecessary policy abstractions or frameworks.
  - [Test Suite]: 11/11 tests in `rbac.test.js` passed, 75/75 total backend test suite passed cleanly.

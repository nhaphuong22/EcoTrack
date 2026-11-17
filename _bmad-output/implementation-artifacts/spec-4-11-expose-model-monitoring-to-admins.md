---
title: 'Story 4.11: Expose model monitoring to admins'
type: 'feature'
created: '2026-11-17'
status: 'done'
baseline_commit: 'cd65ce8ead6c96b74f4b610edcdfdbcbe28fd511'
route: 'oneshot'
review_loop_iteration: 0
story_keys:
  - 4-11-expose-model-monitoring-to-admins
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The monitoring page (Story 4.12) has no gateway route to the AI service's `/internal/mlops/status` (Story 4.10) and `/internal/mlops/retrain` (Story 4.8). `errorHandler` also forwards `err.status` as-is, so an upstream 401 (token mismatch) would reach the browser as a 401 and look like an expired admin session.

**Approach:** Add `backend/src/routes/mlops.js` mounted at `/api/v1/mlops` (behind the existing `authenticate` + `requirePlatformAdmin` perimeter). `GET /status` is a cached pass-through; `POST /retrain` is rate limited, sends no body, forwards 202/409 status and body verbatim, and maps every other upstream failure to a fixed gateway error.

Decisions (Story 4.11 in `epics.md`, Party Mode 2026-11-17):
- Status cache: `InMemoryTTLCache` from `backend/src/utils/cache.js`, TTL `MLOPS_STATUS_CACHE_TTL_SECONDS` (default 5), cleared after every retrain call.
- Retrain rate limit: `MLOPS_RETRAIN_RATE_LIMIT_PER_MINUTE` (default 3), per client IP, 429 `{ detail, status }` without calling the AI service. No new dependency (none exists in `backend/package.json`).
- `champion.status` of `fallback`/`unavailable`/`broken` stays HTTP 200.
- Upstream 202/409 forwarded verbatim (incl. `run_id`). Unreachable → 502, timeout → 504 (`AIServiceError` with `details === null`). Any other upstream non-2xx → 502 `{ detail, status: 502, upstream_status }` with a fixed per-status message; the upstream body is logged server-side only.

</frozen-after-approval>

## Implementation Notes

Files: new `backend/src/routes/mlops.js`; mount in `backend/src/app.js`; two env keys in `backend/.env.example`; new `backend/tests/mlops.test.js` (AI service mocked via `global.fetch`, `adminApp` helper, as in `proxy.test.js`).

Tests must cover: status pass-through incl. `broken`, cache hit and clear after retrain, 202 and 409 verbatim, retrain sent without client body, 429, 502 unreachable, 504 timeout, upstream 401/500 → 502 without leaking the body.

Do not change `aiClient.js` or `errorHandler.js`. Do not run Python training files.

Done: `backend/src/routes/mlops.js`, mount in `app.js`, env keys, `tests/mlops.test.js` (7 tests; backend suite 87/87). The test imports the router through `createRequire` because `app.js` loads it with Node's `require`, so a plain `import` would be a separate instance and `reset()` would not clear the app's state.

## Review Triage Log

- 409 body forwarded unfiltered — low: verbatim 409 is the story's AC; the upstream 409 body is `detail` + `run_id`. Rejected.
- Rate-limit map never evicted, `req.ip` behind a proxy, fixed-window burst — low: only authenticated platform admins reach the route; cost of fixing exceeds the risk. Rejected.
- Stale status re-cached by an in-flight GET after retrain; no single-flight on cold cache — low: bounded by the 5 s TTL. Rejected.
- Authorization untested — false: the route sits under the existing `app.use('/api/v1', authenticate, requirePlatformAdmin)` perimeter, covered by `auth-boundary.test.js`.
- Retrain hardcodes 202 — low: the upstream contract is 202 for accepted. Rejected.
- `.env.example` diff beyond MLOps keys — false: the other lines were already uncommitted before this story; this story added two keys.
- No audit log / API docs / extra untested branches — low. Rejected.
- `details === null` marks own failures — low: `aiClient` sets `details` from `json()` or `text()`, so it is `null` only for a literal JSON `null` upstream body, which FastAPI does not return.

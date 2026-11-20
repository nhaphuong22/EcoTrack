---
title: 'Story 4.12: Monitor the model as an admin'
type: 'feature'
created: '2026-11-21'
status: 'done'
baseline_commit: '88b18239e49b7ced00eba326d074283eed86b418'
route: 'dispatch'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The gateway exposes model status and retrain (Stories 4.10, 4.11) but operators have no page to see model health or trigger a retrain.

**Approach:** Add an "MLOps" tab to the operations dashboard that renders `GET /api/v1/mlops/status`, charts drift and benchmark with Recharts, and lets an `ADMIN` retrain with polling. The tab and the status endpoint are limited to `ADMIN` and to a `MANAGER` of the dashboard's building.

## Boundaries & Constraints

**Always:** Epic 4 Story 4.12 acceptance criteria in `_bmad-output/planning-artifacts/epics.md` are the contract. English UI strings follow the dashboard's Vietnamese labels. Status stays platform-wide (one serving model). Retrain is `ADMIN` only (FR40). Polling pauses while the browser tab is hidden and stops on unmount. Frontend gating mirrors, never replaces, the gateway check.

**Never:** No router, no new backend status field, no `window.confirm` (inline two-step confirm instead), no change to the AI service. Do not tighten `POST /retrain` (already `ADMIN`). TECHNICIAN and managers of other buildings never see the tab.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Allowed viewer | `ADMIN`, or staff `MANAGER` on `office_tower_01` | Tab shown; status renders | N/A |
| Other manager / TECHNICIAN | staff `MANAGER` on another building, or `TECHNICIAN` | Tab hidden; gateway 403 on status | 403 detail shown if reached |
| Champion not resolved | `champion.status` fallback/unavailable/broken | Banner; `broken` shows `error` prominently; metrics empty state | N/A |
| Null / errored section | section `null` or `errors[section]` set | Empty state vs distinct error state; other sections still render | Per-section |
| Retrain accepted | POST returns 202 `{run_id}` | Button disabled; poll status every 4 s until history has `run_id`, or 15 min ceiling | Ceiling shows "still running or unknown" |
| Retrain conflict | 409 (`run_id` may be in body) | "Retrain already running"; start same polling | N/A |
| Retrain refused | 429 / 502 / 504 | Gateway message shown; button re-enabled | Not permanently disabled |
| Idle | Tab open, no retrain | Quiet refresh every 30 s; paused while hidden | Keep last data on failure |

</frozen-after-approval>

## Code Map

- `backend/src/routes/mlops.js` -- status route uses `requireRole('ADMIN','MANAGER')`; replace with ADMIN-or-building-MANAGER check; retrain route unchanged.
- `backend/src/services/authService.js` -- `operatorRole`, `publicUser` (exposes `role` and `staff[{building_id, role}]`); reuse, do not change.
- `backend/tests/mlops.test.js` + `backend/tests/helpers/adminApp.js` -- gateway test pattern (mocked `fetch`, admin `authenticate` stub); add cases with other `req.user` shapes.
- `frontend/src/App.jsx` -- tab state `activeTab` (`dashboard`/`floorplan`), tablist in `Header`; takes no props today; add `user` prop and MLOps tab.
- `frontend/src/AccountPortal.jsx:174` -- renders `<AdminDashboard />` with no props; pass `user`.
- `frontend/src/services/api.js:122-128` -- `fetchMLOpsStatus`, `triggerMLOpsRetrain` already exist; reuse.
- `frontend/src/hooks/useSystemStatus.js` and `components/dashboard/SystemStatus.jsx` -- interval-polling hook and panel style (`panel`, `panel-head`, `chip`, `num`) to copy.
- `frontend/src/components/dashboard/ForecastChart.jsx` -- Recharts conventions to follow.
- Status payload: `champion{status,version,trained_at,metrics,error}`, `drift{checked_at,drift_detected,triggered_signals,signals{<feature>{psi,ks_statistic,...}},rolling_mape{mape_percent},thresholds{psi,mape_percent}}`, `anomaly_quality`, `retrain_history[{run_id,timestamp,trigger,champion_version,challenger_version,outcome,reason}]`, `benchmark{models[{model,mae_kwh,rmse_kwh,mape_percent,r2}]}`, `errors{}`.

## Tasks & Acceptance

**Execution:**
- [x] `backend/src/routes/mlops.js` -- status route allows `ADMIN` or a `MANAGER` staff row on `office_tower_01`, else 403 -- tightens 4.11 per decision
- [x] `backend/tests/mlops.test.js` -- cover other-building manager 403, own-building manager 200, TECHNICIAN 403
- [x] `frontend/src/hooks/useMLOpsStatus.js` -- load status, 30 s idle refresh, 4 s polling while retrain runs, visibility pause, 15 min ceiling, retrain action with 202/409/429/502/504 handling
- [x] `frontend/src/components/dashboard/MLOpsPanel.jsx` -- champion, drift (Recharts PSI bars vs threshold), anomaly P/R/F1, history table, benchmark (Recharts MAPE bars) and table, empty/error states, Retrain with inline confirm for `ADMIN`
- [x] `frontend/src/App.jsx` + `frontend/src/AccountPortal.jsx` -- `user` prop, MLOps tab shown only when allowed
- [x] `frontend/src/__tests__/MLOpsPanel.test.jsx` + `App.test.jsx` -- role gating (tab shown/hidden in App), each champion status, null/errors sections, retrain confirm, fake-timer polling and ceiling, 409/429/502/504

**Acceptance Criteria:**
- Given the AC set for Story 4.12 in `epics.md`, when `npm run test --prefix backend` and the frontend Vitest suite run, then they pass with the new cases
- Given an `ADMIN`, when the tab opens, then all sections render from the mocked payload and Retrain is available

## Implementation Notes

## Spec Change Log

## Review Triage Log

| # | Finding | Verdict | Route | Evidence |
|---|---------|---------|-------|----------|
| 1 | 202/409 without `run_id` tracks `'unknown'`, polls 15 min | medium | patch | Real: `'unknown'` never matched a history row. Fixed: complete on any row not seen at track time; test added |
| 2 | Overlapping `load()` calls can apply an older response | low | patch | Real (interval, visibility tick, refresh). Fixed with a sequence guard |
| 3 | `errors: null` crashes the panel | low | patch | Default only covered `undefined`. Fixed; test added |
| 4 | English notices in a Vietnamese UI | low | patch | Spec says follow Vietnamese labels. Two strings translated, tests updated |
| 5 | Blank "Trạng thái" when `status` is undefined | low | patch | Falls back to a dash |
| 6 | No test that `AccountPortal` passes `user` to the dashboard | medium | patch | Mock ignored props. Mock now exposes `data-role`; ADMIN case asserts it |
| 7 | Hidden-tab test never un-hides the tab | medium | patch | Test now asserts the immediate refetch on visible |
| 8 | No backend test for ADMIN or for a manager calling retrain | low | patch | Both added to `mlops.test.js` |
| 9 | `DASHBOARD_BUILDING` duplicated on both sides | low | defer | Real drift risk, annotated as mirrored; a single source needs shared config |
| 10 | 403 instead of 401 with no `req.user` | false | reject | `authenticate` runs before the router, so `req.user` is always set |
| 11 | Revoked staff keep access | false | reject | `BuildingStaff` has no active or expiry field |
| 12 | `triggered_signals` not an array | false | reject | The 4.10 contract returns a list |
| 13 | Double-click sends two retrains | false | reject | The confirm button disappears on the first click; a 409 is handled |
| 14 | `AdminDashboard` may not forward `user` | false | reject | `React.lazy` forwards props to the default export |
| 15 | `loading &&` change in `App.jsx` is unrelated | false | reject | Pre-existing uncommitted change by the user, not part of this story |
| 16 | Hex colours, raw timestamps, chart a11y, wide table, Cancel/refresh tests | low | reject | Cosmetic or negligible; fixes add guards or components |
| 17 | `App` shows FloorPlan if `showMLOps` turns false while on the tab | low | reject | Needs a prop change mid-session; sign-out unmounts the dashboard |

## Design Notes

The allowed-viewer rule is one predicate used on both sides: `ADMIN` or `staff.some(role === 'MANAGER' && building_id === 'office_tower_01')`. The id matches the dashboard's hard-coded building (`useEnergyData`, `energy.js`); revisit when the dashboard gets a building picker.

## Verification

**Commands:**
- `npm run test --prefix backend` -- expected: all pass
- `npm run test --prefix frontend -- --run` -- expected: all pass

**Manual checks (if no CLI):**
- Sign in as `ADMIN`, open the MLOps tab, press Retrain, confirm, and watch the history gain a row.

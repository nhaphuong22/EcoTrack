---
title: 'Story 5.4: Sign in and navigate by role'
type: 'feature'
created: '2026-11-16'
status: 'done'
story_keys:
  - 5-4-sign-in-and-navigate-by-role
context:
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-EcoTrack-2026-09-23/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-5-1-sign-in-with-a-role.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-5-2-stay-signed-in-and-sign-out.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-5-3-protect-operations-by-role-and-harden-the-gateway.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The EcoTrack frontend currently has no login screen, no session state management, and no role-aware navigation. Any visitor can see the dashboard, and when the backend rejects requests with 401 (token expiration) or 403 (unauthorized role), the frontend simply fails without recovery. Additionally, there is no UI for logging out or switching between roles (`ADMIN`, `MANAGER`, `TECHNICIAN`).

**Approach:**
1. Build `LoginPage.jsx` with a modern dark-mode UI, accessible form inputs for email and password, inline error reporting, and keyboard submission (`Enter`).
2. Implement auth token lifecycle in `src/services/auth.js` and configure Axios interceptors in `src/services/api.js`:
   - Outbound requests automatically attach `Authorization: Bearer <accessToken>`.
   - Inbound 401 responses trigger a single silent token refresh (`POST /api/v1/auth/refresh`), replay the failed request, and redirect to Login only if refresh fails.
3. Integrate session state and role-aware navigation in `App.jsx` and `Header.jsx`:
   - Unauthenticated visitors are presented with the Login page.
   - Upon sign-in, users land on the Dashboard.
   - Navigation bar displays tabs: **Tổng quan Năng lượng** (Dashboard) and **Sơ đồ Mặt bằng 2D** (Floor Plan).
   - The **MLOps** tab is conditionally rendered exclusively for `ADMIN` and `MANAGER` roles; non-admin users (e.g. `TECHNICIAN`) attempting to view or access MLOps are redirected to the Dashboard.
   - Header shows user badge (name and role) and an explicit **Đăng xuất** (Logout) button that invokes `/api/v1/auth/logout`, wipes stored tokens, and returns to the Login view.

## Boundaries & Constraints

**Always:**
- Apply Ponytail Ladder: Simple React state/hook management; avoid external global state stores (Redux, Zustand) or bulky router packages.
- When unauthenticated, render `LoginPage` and do not execute background telemetry polling.
- On login error (wrong email/password), show a clear inline error banner; keep form accessible and responsive to keyboard actions.
- Axios 401 interceptor must use a single-retry guard (`config._retry = true`) to prevent infinite refresh request loops.
- `MLOps` tab must be hidden from `TECHNICIAN` users. If `activeTab === 'mlops'` while user is `TECHNICIAN`, auto-revert to `'dashboard'`.
- Clicking "Đăng xuất" clears `token`, `refreshToken`, and `user` from storage, calls backend logout, and switches view to `LoginPage`.
- Unit tests for `App.test.jsx`, `FloorPlan.test.jsx`, and `SystemStatus.test.jsx` must pass cleanly without regressions.

**Never:**
- Never display the MLOps tab to `TECHNICIAN` role.
- Never store raw passwords or unneeded sensitive profile details in local storage.
- Never lock out keyboard users (form inputs must support standard tab navigation and form submit on Enter).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Unauthenticated visit | App loads, no token in storage | Renders `LoginPage` | Block dashboard access |
| Valid login submission | Enter email & password, submit | Calls `/api/v1/auth/login`, saves tokens, lands on Dashboard | Clear errors |
| Invalid credentials | Submit wrong password | Shows inline error "Invalid email or password", inputs retain focus | Keep form interactive |
| Role Navigation: Admin / Manager | Logged in as `ADMIN` or `MANAGER` | Nav tabs show: Dashboard, Floor Plan, MLOps | All 3 tabs clickable |
| Role Navigation: Technician | Logged in as `TECHNICIAN` | Nav tabs show: Dashboard, Floor Plan only | MLOps tab not visible |
| Direct MLOps access attempt | `TECHNICIAN` attempts to open MLOps | State forces fallback to `dashboard` tab | Prevent unauthorized view |
| Expired Access Token (401) | Any API call fails with 401 | Interceptor calls `/auth/refresh`, gets new token, retries original call | Seamless (silent refresh) |
| Refresh Token Expired / Invalid | Refresh call fails with 401 | Interceptor clears storage and redirects to `LoginPage` | Clean session reset |
| Logout clicked | Click "Đăng xuất" button in Header | Calls `/auth/logout`, clears tokens, immediately renders `LoginPage` | None |

</frozen-after-approval>

## Code Map

- `frontend/src/services/auth.js` (new) — Auth storage helpers:
  - `getStoredAuth()`, `saveAuthTokens(data)`, `clearAuthTokens()`.
  - `loginApi(email, password)`, `refreshApi(refreshToken)`, `logoutApi(refreshToken)`.
- `frontend/src/services/api.js` — Attach Axios request interceptor (Bearer token) and response interceptor (silent refresh on 401 with `_retry` guard).
- `frontend/src/components/auth/LoginPage.jsx` (new) — Login view with dark-theme styling, email/password fields, loading state, and inline error banner.
- `frontend/src/components/dashboard/MLOpsView.jsx` (new) — MLOps status and model management view for Admin and Manager.
- `frontend/src/components/layout/Header.jsx` — Add user role badge and "Đăng xuất" button.
- `frontend/src/App.jsx` — Integrate auth state gate, role-based tab rendering, and fallback redirection.
- `frontend/src/__tests__/Auth.test.jsx` (new) — Vitest test suite for:
  - Unauthenticated redirect to Login.
  - Successful login landing on Dashboard.
  - Role-aware navigation (MLOps visible for Admin/Manager, hidden for Technician).
  - Silent refresh interceptor handling 401.
  - Logout clearing session and returning to Login.
- Existing frontend tests (`App.test.jsx`, `FloorPlan.test.jsx`, `SystemStatus.test.jsx`) — ensure test setup provides mock authenticated session.

## Tasks & Acceptance

**Execution:**
- [x] Create `frontend/src/services/auth.js` for token persistence and API calls — FR41.
- [x] Configure Axios request and response interceptors in `frontend/src/services/api.js` for silent refresh — FR41.
- [x] Create `frontend/src/components/auth/LoginPage.jsx` with accessible form and inline error handling — FR41.
- [x] Create `frontend/src/components/dashboard/MLOpsView.jsx` for Admin/Manager model monitoring — FR40, FR44.
- [x] Update `frontend/src/components/layout/Header.jsx` with user profile pill and "Đăng xuất" button — FR41.
- [x] Update `frontend/src/App.jsx` to enforce login gate, role-based tabs, and direct MLOps redirection — FR41.
- [x] Write integration test suite `frontend/src/__tests__/Auth.test.jsx` and ensure all tests pass.

**Acceptance Criteria:**
- Given I am not signed in,
- When I open any page,
- Then I am redirected to the Login page.
- Given valid credentials,
- When I submit the login form,
- Then I land on the Dashboard, and a navigation bar shows Dashboard and Floor Plan, plus MLOps for `ADMIN` and `MANAGER`.
- Given a non-admin user,
- When they open the MLOps URL directly,
- Then they are redirected to the Dashboard.
- Given an API call returns 401 because the access token expired,
- When the Axios interceptor handles it,
- Then it refreshes the token once, retries the call, and redirects to Login only if the refresh fails.
- Given I click "Đăng xuất",
- When logout completes,
- Then stored tokens are cleared and I am back on the Login page.
- Given wrong credentials,
- When I submit the form,
- Then an inline error is shown and the form stays usable by keyboard.

## Design Notes

- **Ponytail Ladder:** Session state is managed via React `useState`/`useCallback` synchronized with `localStorage`. No heavy state management dependencies (Redux, Zustand, MobX) are introduced.
- **Axios Interceptor Resilience:** A dedicated `isRefreshing` queue or clean single-retry `_retry` flag ensures simultaneous failing requests don't trigger cascading refresh floods.

## Review Triage Log

- **BMAD AC Verification:**
  - [x] Given unauthenticated user -> redirects to `LoginPage` (tested in `Auth.test.jsx`).
  - [x] Given valid credentials -> lands on Dashboard, role badge displayed, tabs visible (tested in `Auth.test.jsx`).
  - [x] Given role matrix: `TECHNICIAN` sees Dashboard & Floor Plan, MLOps hidden; `ADMIN` & `MANAGER` see MLOps; Technician visiting MLOps directly auto-redirects to Dashboard (tested in `Auth.test.jsx`).
  - [x] Given 401 token expiration -> Axios response interceptor performs silent refresh and request replay (tested in `Auth.test.jsx`).
  - [x] Given "Đăng xuất" clicked -> clears tokens, calls `/api/v1/auth/logout`, renders `LoginPage` (tested in `Auth.test.jsx`).
  - [x] Given invalid credentials -> displays inline error banner, keeps inputs keyboard-interactive (tested in `Auth.test.jsx`).
  - [x] 100% test pass rate: 26/26 frontend tests, 75/75 backend tests passing.
- **Ponytail Review (Anti-Overengineering Audit):**
  - Zero heavy external state stores (no Redux, Zustand, MobX, React Router) added.
  - Zero redundant repository layers or single-use abstract interfaces.
  - Interceptors directly integrated in Axios client without complex multi-file proxy wrappers.
- **Ponytail Rating:** 🟢 Lean (Tinh gọn, chuẩn).


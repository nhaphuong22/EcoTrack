---
title: 'Story 5.1: Sign in with a role'
type: 'feature'
created: '2026-11-16'
status: 'done'
story_keys:
  - 5-1-sign-in-with-a-role
context:
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-EcoTrack-2026-09-23/ARCHITECTURE-SPINE.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** EcoTrack currently lacks user authentication and role management. All public gateway endpoints are completely open or guarded only by service-to-service internal tokens. The system cannot identify who is accessing the dashboard, distinguish between administrators, managers, and technicians, or protect administrative actions.

**Approach:** Implement foundational JWT-based authentication for the Express backend:
1. Define the `User` model in Prisma schema (`email`, `password_hash`, `name`, `role`).
2. Add an automated admin bootstrap seeder on backend startup when `ADMIN_EMAIL` and `ADMIN_PASSWORD` are present and the database contains no users.
3. Expose `POST /api/v1/auth/login` to validate user credentials and issue a 15-minute JWT access token containing the user identity and role.
4. Implement a lightweight `requireAuth` middleware to verify Bearer tokens and populate `req.user`.
5. Enforce fail-fast startup behavior in `server.js` when `JWT_SECRET` is missing.

## Boundaries & Constraints

**Always:**
- Apply Ponytail Ladder: reuse Prisma queries directly in controllers/routes; avoid generic repositories, excessive DTO mappers, or interface-per-class abstractions.
- Store passwords securely using bcrypt hashing with a minimum work factor of 10.
- Return HTTP 401 with identical generic error messages (`"Invalid email or password"`) for both non-existent emails and incorrect passwords to prevent user enumeration.
- Access token validity is strictly 15 minutes (`15m`). Token payload must contain `sub` (or `id`), `email`, `role`, and `name`.
- `requireAuth` middleware must parse the `Authorization: Bearer <token>` header, verify the token using `JWT_SECRET`, and attach decoded user claims to `req.user`.
- Fail fast on server startup in `server.js` if `process.env.JWT_SECRET` is not set, logging a clear diagnostic message and exiting with code 1.
- Unit and integration tests must run cleanly using an in-memory/mock Prisma client or isolated test database with a known test `JWT_SECRET`.

**Never:**
- Never return `password_hash` in API responses or logs.
- Never implement refresh token logic in this story (deferred strictly to Story 5.2).
- Never protect all existing domain routes in this story (route lockdown across `/api/v1/*` is deferred strictly to Story 5.3).
- Never allow fallback secrets for `JWT_SECRET` in production code.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Valid login | `POST /api/v1/auth/login` with correct email & password | HTTP 200, `{ token, user: { id, email, name, role } }` | None |
| Non-existent email | `POST /api/v1/auth/login` with unregistered email | HTTP 401 `{"error": "Invalid email or password"}` | Return identical 401 message |
| Wrong password | `POST /api/v1/auth/login` with wrong password | HTTP 401 `{"error": "Invalid email or password"}` | Return identical 401 message |
| Missing/invalid body | `POST /api/v1/auth/login` with missing fields or invalid email | HTTP 400 `{"error": "Validation failed", "details": ...}` | Zod schema validation error |
| Token validation success | Request with `Authorization: Bearer <valid_token>` | Calls `next()`, `req.user` populated with claims | None |
| Missing auth header | Request with no `Authorization` header | HTTP 401 `{"error": "Authentication token required"}` | Stop request processing |
| Malformed / expired token | Request with invalid or expired Bearer token | HTTP 401 `{"error": "Invalid or expired token"}` | Stop request processing |
| Startup without `JWT_SECRET` | Backend starts with `process.env.JWT_SECRET` unset | Process exits with code 1 and error message | Fail-fast in `server.js` |
| First boot admin seed | Backend starts with `ADMIN_EMAIL` & `ADMIN_PASSWORD`, DB empty | One `ADMIN` user created with hashed password | Logs admin creation |
| Subsequent boot seed | Backend starts, `User` table already has records | No duplicate admin created | Skip seeding |

</frozen-after-approval>

## Code Map

- `backend/prisma/schema.prisma` — Add `User` model:
  - `id`: String UUID / cuid (`@id @default(uuid())`)
  - `email`: String (`@unique @db.VarChar(100)`)
  - `password_hash`: String (`@map("password_hash") @db.VarChar(255)`)
  - `name`: String (`@db.VarChar(100)`)
  - `role`: String (`@default("TECHNICIAN") @db.VarChar(20)`) — valid values: `ADMIN`, `MANAGER`, `TECHNICIAN`
  - `created_at`: DateTime (`@default(now()) @map("created_at") @db.Timestamptz`)
  - Map to table `users`.
- `backend/package.json` — Add `jsonwebtoken` and `bcryptjs`.
- `backend/src/routes/auth.js` — Implement authentication endpoints:
  - Zod validation for `loginSchema`.
  - `POST /login`: Query user via Prisma, compare password with `bcrypt.compare`, sign 15m JWT, return token and sanitized profile.
- `backend/src/middleware/requireAuth.js` — Middleware extracting Bearer token from header, verifying with `jsonwebtoken`, attaching user payload to `req.user`, handling expired/malformed errors.
- `backend/src/services/authService.js` — Direct Prisma helper for admin bootstrapping (`seedDefaultAdminIfNeeded`).
- `backend/src/app.js` — Register `/api/v1/auth` route (`app.use('/api/v1/auth', authRouter)`).
- `backend/src/server.js` — Validate `JWT_SECRET` at boot; invoke `seedDefaultAdminIfNeeded()` after DB connection.
- `backend/tests/auth.test.js` — Vitest integration test suite for login, error cases, seeding, and `requireAuth`.

## Tasks & Acceptance

**Execution:**
- [x] Update `backend/prisma/schema.prisma` with `User` model and run `npx prisma generate` — FR33.
- [x] Install `jsonwebtoken` and `bcryptjs` dependencies in `backend/package.json`.
- [x] Create `backend/src/middleware/requireAuth.js` verifying Bearer JWT access tokens — FR34.
- [x] Create `backend/src/services/authService.js` with `seedDefaultAdminIfNeeded()` — FR33, NFR1.
- [x] Create `backend/src/routes/auth.js` with `POST /login` and wire it up in `backend/src/app.js` — FR34.
- [x] Add `JWT_SECRET` fail-fast validation and seeder call to `backend/src/server.js` — NFR1.
- [x] Add unit and endpoint tests in `backend/tests/auth.test.js`.

**Acceptance Criteria:**
- Given a migration adding `User` with `email` (unique), `password_hash`, `name` and `role` (`ADMIN`, `MANAGER` or `TECHNICIAN`),
- When the backend starts with `ADMIN_EMAIL` and `ADMIN_PASSWORD` set and no users in the database,
- Then one admin user is created with a bcrypt-hashed password.
- Given valid credentials,
- When `POST /api/v1/auth/login` is called,
- Then a JWT access token valid for 15 minutes is returned containing user id and role, along with the user profile.
- Given a wrong email or password,
- When login is called,
- Then the response is 401 with the exact same message in both cases.
- Given a `requireAuth` middleware,
- When a request carries a valid access token,
- Then `req.user` is populated, and missing, malformed or expired tokens return 401.
- Given `JWT_SECRET` is not set,
- When the backend starts outside the test environment,
- Then it fails at startup with a clear message naming `JWT_SECRET`.

## Design Notes

- **Ponytail Ladder:** To keep code lean and prevent bloated abstractions, auth logic does not introduce generic repositories, unit-of-work patterns, or decoupled interface layers. Prisma Client is used directly in `auth.js` and `authService.js`.
- **Token Security:** `expiresIn: '15m'` ensures short-lived access credentials. Refresh tokens will be introduced separately in Story 5.2.

## Review Triage Log

- 2026-11-16: Code Review completed via `/bmad-code-review` and `/ponytail-review`.
  - [BMAD Criteria]: 100% AC achieved. User model persisted, admin seeding verified, 15m JWT issued, timing attack/enumeration safe (constant 401 error message), requireAuth verifies Bearer token, fail-fast checks active in `server.js`.
  - [Ponytail Review]: Score 🟢 **Lean**. Direct Prisma queries without unnecessary wrapper classes or generic repository layers. Diff is minimal and targeted.
  - [Test Suite]: 10/10 auth tests passed, 57/57 total backend test suite passed cleanly.

---
title: 'Story 5.2: Stay signed in and sign out'
type: 'feature'
created: '2026-11-16'
status: 'done'
story_keys:
  - 5-2-stay-signed-in-and-sign-out
context:
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-EcoTrack-2026-09-23/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-5-1-sign-in-with-a-role.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Access tokens issued in Story 5.1 expire strictly after 15 minutes. Without a token refresh mechanism, building operators and technicians are forcibly logged out mid-shift, disrupting monitoring workflows. Furthermore, there is currently no way to revoke a session on logout, leaving valid tokens vulnerable until expiration.

**Approach:** Implement a robust session lifecycle with Refresh Tokens and Refresh Token Rotation (RTR):
1. Create the `RefreshToken` model in Prisma storing a SHA256 cryptographic hash of opaque random tokens with expiry and revocation timestamps.
2. Update `POST /api/v1/auth/login` to issue both a 15-minute JWT access token and a 7-day opaque refresh token.
3. Expose `POST /api/v1/auth/refresh` to rotate sessions: issues a new access token and a new refresh token while revoking the presented refresh token.
4. Enforce Token Reuse Detection: If an already-rotated/revoked refresh token is presented again, immediately revoke all active refresh tokens of that user to mitigate token theft attacks, returning HTTP 401.
5. Expose `POST /api/v1/auth/logout` to explicitly revoke the user's active refresh token.

## Boundaries & Constraints

**Always:**
- Apply Ponytail Ladder: Use Node.js built-in `crypto` for token generation and SHA256 hashing. Query database directly via Prisma without wrapper abstractions.
- Store only the SHA256 hash of refresh tokens in the database (`token_hash = sha256(raw_token)`). Raw tokens are never persisted in database tables or logs.
- Refresh token lifespan is strictly 7 days (`7 * 24 * 60 * 60 * 1000`).
- Token Rotation (RTR): Every call to `POST /api/v1/auth/refresh` revokes the old refresh token (`revoked_at = now()`) and produces a new refresh token and access token.
- Reuse Detection: If a presented token already has `revoked_at != null`, treat this as a replay attack. Revoke all unrevoked refresh tokens belonging to that `user_id` and return 401 `{"error": "Invalid or expired refresh token"}`.
- Logout: Calling `POST /api/v1/auth/logout` with a valid refresh token marks it revoked (`revoked_at = now()`), ensuring it can never be exchanged for a new session.

**Never:**
- Never persist raw refresh token strings in the database.
- Never issue a new access token if the refresh token is expired, revoked, or non-existent.
- Do not add complex Redis session stores or stateful distributed caches; PostgreSQL via Prisma is the single source of truth for token hashes.
- Do not modify domain route access control in this story (broad route protection is reserved for Story 5.3).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Login Success | Valid credentials on `POST /api/v1/auth/login` | 200 `{ token, refreshToken, user }` (refreshToken valid 7 days, hash persisted) | None |
| Refresh Success | `POST /api/v1/auth/refresh` with valid, unrevoked `refreshToken` | 200 `{ token, refreshToken, user }` (old token revoked, new token stored) | None |
| Refresh with Expired Token | `POST /api/v1/auth/refresh` where `expires_at < now()` | 401 `{"error": "Invalid or expired refresh token"}` | Reject exchange |
| Refresh with Unknown Token | `POST /api/v1/auth/refresh` with unrecognized token | 401 `{"error": "Invalid or expired refresh token"}` | Reject exchange |
| Token Reuse Detection (Replay) | `POST /api/v1/auth/refresh` with an already rotated token (`revoked_at != null`) | 401 `{"error": "Invalid or expired refresh token"}` | Revoke all remaining active tokens of that user |
| Missing Refresh Token | `POST /api/v1/auth/refresh` with empty body or null token | 400 `{"error": "Validation failed", ...}` | Zod validation error |
| Logout Success | `POST /api/v1/auth/logout` with active `refreshToken` | 200 `{"message": "Logged out successfully"}` | Token `revoked_at` set to now |
| Logout Idempotency | `POST /api/v1/auth/logout` with already revoked or missing token | 200 `{"message": "Logged out successfully"}` or 400 validation error | Clean response |

</frozen-after-approval>

## Code Map

- `backend/prisma/schema.prisma`:
  - Add `RefreshToken` model (`id`, `user_id`, `token_hash`, `expires_at`, `revoked_at`, `created_at`).
  - Add relation `refresh_tokens RefreshToken[]` on `User`.
- `backend/src/utils/tokenUtils.js` (or helper within `src/routes/auth.js`):
  - `generateRefreshToken()`: Generate random 40-byte hex string.
  - `hashToken(token)`: SHA256 digest of token string.
- `backend/src/routes/auth.js`:
  - Update `POST /login`: Generate and persist refresh token hash, return `refreshToken`.
  - Add `POST /refresh`: Validate input, hash token, find record, verify expiry and revocation status; if reused, revoke all user's tokens; otherwise rotate token and return new access & refresh tokens.
  - Add `POST /logout`: Hash token, set `revoked_at: new Date()`, return success.
- `backend/tests/auth.test.js`:
  - Add test suites for refresh token issuance at login, successful rotation, reuse detection (family revocation), expired token handling, and logout.

## Tasks & Acceptance

**Execution:**
- [x] Add `RefreshToken` model to `backend/prisma/schema.prisma` and run `npx prisma generate` — FR33.
- [x] Implement refresh token generation and SHA256 hashing utilities — FR33, NFR1.
- [x] Update `POST /api/v1/auth/login` to create and return `refreshToken` — FR34.
- [x] Implement `POST /api/v1/auth/refresh` with Token Rotation and Reuse Detection — FR34.
- [x] Implement `POST /api/v1/auth/logout` to revoke tokens on demand — FR34.
- [x] Add unit and integration tests covering rotation, replay detection, and logout in `backend/tests/auth.test.js`.

**Acceptance Criteria:**
- Given a migration adding `RefreshToken` with `user_id`, `token_hash`, `expires_at` and `revoked_at`,
- When I log in,
- Then I also receive a refresh token valid for 7 days, and only its hash is stored in the database.
- Given a valid refresh token,
- When I call `POST /api/v1/auth/refresh`,
- Then I receive a new access token and a new refresh token, and the old refresh token is marked as revoked.
- Given a refresh token that was already rotated,
- When it is presented again,
- Then the response is 401 and all refresh tokens of that user are revoked.
- Given a signed-in user,
- When I call `POST /api/v1/auth/logout` with my refresh token,
- Then that token is revoked and can no longer be used.

## Design Notes

- **Ponytail Ladder:** Token generation uses Node.js standard `crypto.randomBytes(40).toString('hex')` and `crypto.createHash('sha256')`. No external heavyweight session libraries or Redis infrastructure are added.
- **Reuse Detection Strategy:** Preserving `revoked_at` rather than immediately deleting records enables proactive detection of token theft. When a compromised token is replayed, invalidating the entire user token family immediately neutralizes the attacker's access.

## Review Triage Log

- 2026-11-16: Code Review completed via `/bmad-code-review` and `/ponytail-review`.
  - [BMAD Criteria]: 100% AC achieved. RefreshToken model with SHA-256 hash storage, 7-day TTL, automatic rotation upon `/refresh`, token replay detection revokes family tokens on reuse, explicit revocation on `/logout`.
  - [Ponytail Review]: Score 🟢 **Lean**. Uses standard Node.js `crypto` with direct Prisma queries; zero unnecessary layers or external session infrastructure.
  - [Test Suite]: 17/17 auth test cases passed, 64/64 total backend test suite passed cleanly.

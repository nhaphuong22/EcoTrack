---
title: 'Story 1.6: Enforce the internal service token'
type: 'feature'
created: '2026-10-09'
status: 'done'
baseline_commit: '7e1c8a4b4cdfe5ea9b89d61fa8e3106c1709beaa'
route: 'dispatch'
review_loop_iteration: 1
story_keys:
  - 1-6-enforce-the-internal-service-token
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The AI service (FastAPI) mounts every router under `/internal/*` (`energy`, `forecast`, `anomalies`, `copilot`) with no authentication — `main.py` only adds permissive CORS (`allow_origins=["*"]`). Anyone who can reach the service bypasses the gateway and hits the models and the LLM directly. The gateway already sends `X-Internal-Token` (`aiClient.js:21`) but the AI service never checks it, and the gateway falls back to a hardcoded secret `'ecotrack_internal_secret_2026'` (`aiClient.js:2`) when `INTERNAL_API_KEY` is unset — a default secret that also ships in `.env.example` (root + `backend/`) and `docker-compose.yml`. FR17 requires the AI service to reject `/internal/*` requests lacking a valid token, with no default secret shipped; NFR1 makes the shared secret the boundary between the public gateway and the internal engine.

**Approach:** Enforce the shared `INTERNAL_API_KEY` as `X-Internal-Token` on every `/internal/*` request in the AI service (401 on missing/wrong, constant-time compare), leaving `/health` and `/` open. Make both services require `INTERNAL_API_KEY` at real startup and fail fast with a clear message when it is absent, and delete the hardcoded fallback from the gateway so no default secret ships. The fail-fast lives in each service's real-start path (`server.js` for the gateway, the `__main__`/uvicorn launch for the AI service) so that test suites — which import the app object directly — are unaffected, while a started process without the key stops immediately.

## Boundaries & Constraints

**Always:**
- Every `/internal/*` route on the AI service requires `X-Internal-Token` equal to the configured `INTERNAL_API_KEY`; a missing or wrong value returns 401 `{"detail": ..., "code": "ERR_UNAUTHORIZED"}`. The comparison is constant-time (`hmac.compare_digest`).
- `/health` and `/` on the AI service stay reachable with no token.
- A correct token is served normally — existing response shapes and status codes for `/internal/*` are unchanged.
- The gateway sends `X-Internal-Token: <INTERNAL_API_KEY>` on every `callAIService` request (it already does; keep it), reading the key from the environment with **no** hardcoded fallback.
- Both services require `INTERNAL_API_KEY` when actually started (gateway `server.js`; AI service uvicorn `__main__`). If it is unset, the process logs a clear message naming `INTERNAL_API_KEY` and exits non-zero before serving.
- Tests pass with no real secret configured in the environment: suites set a known test `INTERNAL_API_KEY` themselves and send the matching header; the fail-fast never triggers under tests because tests import the app object and never run the real-start path.
- No default or example-real secret ships in code or config: the literal `ecotrack_internal_secret_2026` is gone from `aiClient.js`, `.env.example` (root + `backend/`), and `docker-compose.yml` (replaced by a required/placeholder value, not a working default).

**Never:**
- Never hardcode, default, or log the secret value. `.env.example` uses an obvious placeholder (e.g. `change-me-internal-token`), never a usable default.
- Never require a token on `/health` or `/` (liveness must not depend on the secret).
- Do not change the gateway's public `/api/v1/*` contract, the response bodies of the AI endpoints, or any model/serving logic.
- Do not add a new auth scheme (JWT, OAuth, per-user keys); this is a single shared service-to-service secret only.
- Do not weaken CORS handling as part of this story (out of scope), and do not touch Story 1.1–1.5 serving/anomaly/forecast logic beyond adding the guard.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Valid token | `X-Internal-Token` == `INTERNAL_API_KEY`, any `/internal/*` route | 200 (or the route's normal status); response unchanged | N/A |
| Missing token | No `X-Internal-Token` on an `/internal/*` route | 401 `{"detail": ..., "code": "ERR_UNAUTHORIZED"}` | Request not served by the handler |
| Wrong token | `X-Internal-Token` != `INTERNAL_API_KEY` | 401 `{"detail": ..., "code": "ERR_UNAUTHORIZED"}` | Constant-time compare; not served |
| Health open | `GET /health` (and `GET /`) with no token | 200 | Never guarded |
| AI service start, key unset | uvicorn `__main__` launched, `INTERNAL_API_KEY` absent | Process logs a clear message naming `INTERNAL_API_KEY` and exits non-zero before serving | No server started |
| Gateway start, key unset | `node src/server.js`, `INTERNAL_API_KEY` absent | `server.js` logs a clear message and exits non-zero before `listen` | No server started |
| Gateway → AI happy path | Gateway proxies with the configured key | AI service serves; gateway returns the proxied body | N/A |
| Test env | Suites import the app object, set a test key, send the header | All existing endpoint tests pass; fail-fast does not fire | N/A |

</frozen-after-approval>

## Code Map

- `ai-service/src/config.py` — add `get_internal_api_key() -> str | None` reading `INTERNAL_API_KEY` from the environment (no default). Reuse the existing `os.getenv` pattern (as `get_tariff_rate_*`/`get_models_dir` do).
- `ai-service/src/main.py` — add an HTTP middleware (or equivalent) that, for request paths starting with `/internal/`, reads `X-Internal-Token` and compares it to `get_internal_api_key()` with `hmac.compare_digest`; on mismatch/missing, return `JSONResponse(status_code=401, {"detail": ..., "code": "ERR_UNAUTHORIZED"})`. `/health` and `/` bypass. Add the fail-fast in the `if __name__ == "__main__"` block (before `uvicorn.run`): if `get_internal_api_key()` is falsy, print a clear message naming `INTERNAL_API_KEY` and `sys.exit(1)`. Keep the existing exception handlers and router mounts.
- `ai-service/tests/conftest.py` — set a session `INTERNAL_API_KEY` (e.g. `test-internal-token`) in `os.environ` alongside the existing `ECOTRACK_*` env, restored in teardown.
- `ai-service/tests/test_smoke.py` — the `client` fixture attaches a default `X-Internal-Token` header (matching conftest's key) so all existing `/internal/*` endpoint tests keep passing; add tests: missing token → 401 `ERR_UNAUTHORIZED`, wrong token → 401, and `/health` (and `/`) reachable with no token. (A raw `TestClient(app)` with no default header exercises the 401 paths.)
- `backend/src/utils/aiClient.js` — line 2: remove the `|| 'ecotrack_internal_secret_2026'` fallback. Read `INTERNAL_API_KEY` from `process.env` (prefer reading it inside `callAIService` so test setup can set it before use); keep sending it as `X-Internal-Token` (line 21).
- `backend/src/server.js` — before `app.listen`, validate `process.env.INTERNAL_API_KEY`; if absent, `console.error` a clear message naming `INTERNAL_API_KEY` and `process.exit(1)`. (`app.js` stays import-safe for tests — no validation there.)
- `backend/tests/` — ensure the vitest run has `INTERNAL_API_KEY` set so `aiClient` sends a string (satisfies `proxy.test.js:41` `X-Internal-Token: expect.any(String)`). Add a `backend/vitest.config.js` with `setupFiles: ['./tests/setup.js']` (new) that sets `process.env.INTERNAL_API_KEY`, or set it at the top of the affected test(s). No gateway test runs `server.js`, so the fail-fast is not exercised there.
- `.env.example` (root + `backend/.env.example`) and `docker-compose.yml` (lines ~35, ~62) — replace the literal `ecotrack_internal_secret_2026` with a non-working placeholder / required variable so no usable default ships.
- `ai-service/src/main.py` routers (`energy`/`forecast`/`anomalies`/`copilot`, all `/internal/*`) — consumers of the guard; no change to the routers themselves.

## Tasks & Acceptance

**Execution:**
- [x] `ai-service/src/config.py` — add `get_internal_api_key()` (env-only, no default) — FR17/NFR1.
- [x] `ai-service/src/main.py` — add `/internal/*` token-enforcement middleware (401 `ERR_UNAUTHORIZED`, constant-time compare, `/health` + `/` open) and a `__main__` startup fail-fast when `INTERNAL_API_KEY` is unset — FR17, NFR1.
- [x] `ai-service/tests/conftest.py` — set a session `INTERNAL_API_KEY` test value (restored in teardown).
- [x] `ai-service/tests/test_smoke.py` — default-token `client` fixture; add missing-token 401, wrong-token 401, and `/health`-open (no token) tests.
- [x] `backend/src/utils/aiClient.js` — remove the hardcoded fallback secret; read `INTERNAL_API_KEY` from env and send it as `X-Internal-Token`.
- [x] `backend/src/server.js` — startup fail-fast (clear message + non-zero exit) when `INTERNAL_API_KEY` is unset.
- [x] `backend/vitest.config.js` + `backend/tests/setup.js` (new) — set `INTERNAL_API_KEY` for the vitest run so `aiClient` sends a string and `proxy.test.js` passes.
- [x] `.env.example` (root + `backend/`) and `docker-compose.yml` — replace the default secret with a placeholder / required variable (no usable default ships) — FR17.

**Acceptance Criteria:**
- Given `INTERNAL_API_KEY` is configured, when a request reaches any `/internal/*` route without `X-Internal-Token` or with a wrong value, then the AI service responds 401.
- Given a request carries the correct token, when it reaches an `/internal/*` route, then it is served normally, and `/health` stays reachable without a token.
- Given `INTERNAL_API_KEY` is not set, when either service starts outside the test environment, then it fails at startup with a clear message, and the fallback secret `ecotrack_internal_secret_2026` no longer exists in `backend/src/utils/aiClient.js`.

## Implementation Notes

- At authoring time the Story 1.5 code-review patches are uncommitted in the working tree on `feature/epic-1-foundation`; `baseline_commit` is the Story 1.5 commit `7e1c8a4`. Commit the working tree before running the build so Story 1.6's diff is clean.

## Spec Change Log

## Review Triage Log

- 2026-10-09: 3-layer review completed (blind-hunter, edge-case-hunter, verification-gap).
  - Blind Hunter: Verified token enforcement middleware in `ai-service/src/main.py` guards `/internal` and `/internal/*` cleanly. Verified `/health` and `/` bypass without token requirement. Verified constant-time comparison via `hmac.compare_digest` with explicit guards against `None`.
  - Edge-case Hunter: Missing header, incorrect header value, missing environment key all return 401 `ERR_UNAUTHORIZED`. Verified startup fail-fast cleanly terminates with code 1 and descriptive error message in both `ai-service/src/main.py` and `backend/src/server.js`.
  - Verification Gap: All 60 pytest tests pass in `ai-service`. All 38 vitest tests pass in `backend`. Git grep verified zero occurrences of `ecotrack_internal_secret_2026` in `backend`, `ai-service`, `.env.example`, and `docker-compose.yml`.

## Design Notes

- **Where the guard lives:** a single path-prefix middleware in `main.py` covers all four `/internal/*` routers uniformly and keeps `/health`/`/` open, rather than adding a dependency to every route. A FastAPI dependency would also work but must be attached to each router; the middleware is one choke point.
- **Test environment = import, not run:** both services already separate the app object (imported by tests: `TestClient(app)`, `supertest(app)`) from the real-start path (`uvicorn __main__`, `server.js`). Putting the fail-fast only in the real-start path satisfies "fails at startup outside the test environment" without a bespoke env flag, and keeps suites green. Token *enforcement* still runs under tests, so suites set a known `INTERNAL_API_KEY` and send the header.
- **Constant-time compare:** use `hmac.compare_digest(provided, expected)` to avoid leaking the secret via timing; guard against `None` (missing header) first.
- **Error envelope:** reuse the project's `{"detail", "code"}` convention (`ERR_UNAUTHORIZED`), consistent with the 503/422 handlers already in `main.py`.
- **No default secret:** `.env.example` and `docker-compose.yml` must not carry a working secret; a placeholder makes misconfiguration fail loudly at startup rather than silently running on a known value.

## Verification

**Commands:**
- `cd ai-service && python -m pytest -q` — expected: all pass, including new 401 (missing/wrong token) and `/health`-open tests; existing `/internal/*` tests pass via the default-token client fixture.
- `npm run test --prefix backend` — expected: all pass; `proxy.test.js` still sees `X-Internal-Token` as a string (from test setup); no test runs `server.js`.
- `cd ai-service && INTERNAL_API_KEY= python -c "import runpy,sys; sys.argv=['m']; runpy.run_module('src.main', run_name='__main__')"` — expected: clear error naming `INTERNAL_API_KEY`, non-zero exit (no server start). *(Or inspect the `__main__` block.)*
- `grep -rn "ecotrack_internal_secret_2026" backend ai-service .env.example docker-compose.yml` — expected: no matches.

### Review Findings

3-layer review completed at Ponytail full / standard library level. 0 intent gaps, 0 bugs, 0 patches needed. All 4 verification commands tested and verified green. All acceptance criteria satisfied.

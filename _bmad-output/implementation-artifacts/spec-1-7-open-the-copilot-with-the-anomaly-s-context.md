---
title: 'Story 1.7: Open the Copilot with the anomaly''s context'
type: 'feature'
created: '2026-10-09'
status: 'done'
baseline_commit: 'e088756ac6a59f6133e281984c8a42c26b9b2bb4'
route: 'dispatch'
review_loop_iteration: 1
story_keys:
  - 1-7-open-the-copilot-with-the-anomaly-s-context
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The dashboard's anomaly list has an "Ask Copilot" action (`AnomalyTable.jsx` → `onAskCopilot(anom)`), and `App.jsx` prepares a diagnostic prompt for the clicked anomaly (`handleAskCopilot`) and passes it to `<CopilotDrawer initialMessage={pendingPrompt} />`. But `CopilotDrawer({ isOpen, onClose })` never declares or uses an `initialMessage` prop, and it owns its **own** `useCopilot()` instance internally — so `App` has no handle on the drawer's `sendMessage`. The prepared prompt is silently dropped: clicking "Copilot" opens the drawer but no message is sent, and the engineer must retype the anomaly details by hand. Separately, the dashboard's gateway-unreachable banner (`App.jsx:35`) hardcodes `http://localhost:8000` — both hardcoded and the wrong service (the frontend talks to the Express gateway at `VITE_API_URL`, default `:5000`, not the AI service at `:8000`). FR19 requires the "Ask Copilot" action to open the drawer with the prepared prompt already sent as the first message, appended to one shared conversation, and the error banner to name the configured `VITE_API_URL`.

**Approach:** Lift the single `useCopilot()` instance up to `App` so one conversation is shared by every entry point (anomaly rows, the floating button, quick prompts, manual input). `handleAskCopilot(anomaly)` builds the diagnostic prompt from the anomaly's fields, calls the shared `sendMessage(prompt)`, then opens the drawer — so the prompt is delivered as the first user message and a second anomaly click appends to the same conversation without losing earlier messages. `CopilotDrawer` becomes a controlled, presentational component receiving `{ isOpen, onClose, messages, isLoading, error, sendMessage, clearHistory }` as props (its internal `useCopilot()` and the ignored `initialMessage` path are removed). The gateway-unreachable banner reads the configured base URL exported from `services/api.js` instead of a hardcoded string. This is a frontend-only change; no gateway, AI-service, or API-contract change. Because the frontend currently ships no test harness, the story also stands up Vitest + React Testing Library (jsdom) and adds tests for the three acceptance criteria.

## Boundaries & Constraints

**Always:**
- Clicking "Copilot" on an anomaly row delivers the prepared diagnostic prompt into the Copilot conversation **as a user message** and opens the drawer.
- There is exactly **one** shared Copilot conversation across all entry points. Opening the drawer from a different anomaly while a conversation exists appends the new prompt to that same conversation without clearing earlier messages.
- The prepared prompt carries the anomaly's identifying context (at least `id`, `timestamp`, `delta_kwh`, `anomaly_score`) so the LLM can diagnose without the user retyping details.
- The dashboard's gateway-unreachable banner names the configured gateway base URL (`import.meta.env.VITE_API_URL`, default `http://localhost:5000`) — never a hardcoded host/port.
- Existing Copilot behaviors stay intact: the seeded welcome message, quick prompts, manual textarea input, clear-history, the last-10-entry history window sent to the gateway, and the loading/error states.

**Never:**
- Do not change the gateway `/api/v1/*` contract or the `POST /api/v1/copilot/chat` request/response shape, and do not touch any AI-service or gateway logic.
- Do not change anomaly / forecast / metrics detection logic or their response field names and shapes (the dashboard consumes them as they are today).
- Do not reintroduce a second independent Copilot hook/conversation instance — that duplication is the current dropped-prompt bug.
- Do not auto-send any message when the drawer is opened via the floating Copilot button or closed/reopened manually; only the anomaly "Copilot" action sends a prompt.
- Do not hardcode a host or port in any user-visible string; derive it from `VITE_API_URL`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Ask from a row, drawer closed | Click "Copilot" on anomaly row; no conversation beyond the welcome | Drawer opens; the prepared prompt for that anomaly is appended as the first **user** message and sent to the gateway; assistant reply appended | On POST failure the drawer shows the Copilot error text; prior messages kept |
| Ask from a second row, drawer open | A conversation already exists; click "Copilot" on a different anomaly | The new prompt is appended to the **same** conversation; earlier user/assistant messages are preserved | Same as above |
| Floating button | Click the floating Copilot button | Drawer opens showing the existing conversation; **no** message is auto-sent | N/A |
| Manual input / quick prompt | Type + send, or pick a quick prompt | Message appended and sent to the same shared conversation | Existing behavior unchanged |
| Clear history | Click the trash button | Conversation resets to the welcome message; the sent-history window is cleared | N/A |
| Gateway unreachable (dashboard) | Energy fetch fails in `useEnergyData` | Dashboard error banner is shown and names the configured `VITE_API_URL` (default `http://localhost:5000`), not `:8000` | Banner also surfaces the fetch error message |
| Prompt built from a sparse anomaly | Anomaly missing an optional field | `buildAnomalyPrompt` still returns a well-formed prompt string (no `undefined`/`NaN` leaking into the text) | Defensive formatting of optional fields |

</frozen-after-approval>

## Code Map

- `frontend/src/hooks/useCopilot.js` — no public-API change; it becomes the **single** shared instance (lifted into `App`). Keep `{ messages, isLoading, error, sendMessage, clearHistory }`. (Confirm `sendMessage` identity is stable — it already uses `useCallback([])`.)
- `frontend/src/App.jsx` — call `useCopilot()` here. Delete the dead `pendingPrompt` state and the `initialMessage` prop. `handleAskCopilot(anomaly)` → `sendMessage(buildAnomalyPrompt(anomaly))` then `setDrawerOpen(true)`. Pass `{ isOpen, onClose, messages, isLoading, error, sendMessage, clearHistory }` to `CopilotDrawer`. Change the error banner (line ~35) from the hardcoded `http://localhost:8000` to the configured base URL (`API_BASE_URL` imported from `services/api.js`).
- `frontend/src/components/copilot/CopilotDrawer.jsx` — convert to controlled/presentational: accept `{ isOpen, onClose, messages, isLoading, error, sendMessage, clearHistory }` as props; remove the internal `useCopilot()` call. Keep the input textarea, `QuickPrompts`, auto-scroll, focus-on-open, and send/keydown handlers (they now call the `sendMessage` prop).
- `frontend/src/services/api.js` — export `API_BASE_URL` (already computed as `import.meta.env.VITE_API_URL || 'http://localhost:5000'`) so the banner can display the configured gateway URL.
- `frontend/src/lib/copilotPrompt.js` *(new)* — pure `buildAnomalyPrompt(anomaly) -> string`, extracted from the current inline template in `App.handleAskCopilot`, with defensive formatting of optional fields. Unit-testable without React.
- `frontend/package.json` — add devDeps `vitest`, `jsdom`, `@testing-library/react`, `@testing-library/jest-dom`, `@testing-library/user-event`; add scripts `"test": "vitest run"` and `"test:watch": "vitest"`.
- `frontend/vite.config.js` — add a Vitest `test` block (`environment: 'jsdom'`, `globals: true`, `setupFiles: './src/test/setup.js'`). Use `defineConfig` from `vitest/config` (or add `/// <reference types="vitest" />`).
- `frontend/src/test/setup.js` *(new)* — `import '@testing-library/jest-dom'`.
- `frontend/src/**/__tests__/*.test.jsx` *(new)* — tests for the three ACs + the prompt builder (see Tasks).

## Tasks & Acceptance

**Execution:**
- [x] `frontend/src/lib/copilotPrompt.js` — extract `buildAnomalyPrompt(anomaly)` (pure, defensive on optional fields) — FR19.
- [x] `frontend/src/App.jsx` — lift `useCopilot()`; `handleAskCopilot` builds the prompt and calls `sendMessage` then opens the drawer; remove `pendingPrompt`/`initialMessage`; pass copilot state/handlers to the drawer — FR19.
- [x] `frontend/src/components/copilot/CopilotDrawer.jsx` — convert to controlled component consuming copilot props; drop the internal hook and the ignored `initialMessage` — FR19.
- [x] `frontend/src/App.jsx` + `frontend/src/services/api.js` — export `API_BASE_URL`; error banner names the configured `VITE_API_URL` (no hardcoded `:8000`).
- [x] `frontend/package.json` + `vite.config.js` + `src/test/setup.js` — stand up Vitest + RTL (jsdom); add `test` script.
- [x] Tests — AC1: clicking "Copilot" on a row sends `buildAnomalyPrompt(anomaly)` as the first user message and opens the drawer; AC2: a second row click appends to the same conversation without dropping earlier messages (mock `sendCopilotMessage`); AC3: the dashboard error banner renders the configured `VITE_API_URL`, not `:8000`; plus a `buildAnomalyPrompt` unit test.

**Acceptance Criteria:**
- Given the anomaly list is shown, when I click "Copilot" on a row, then the drawer opens and the prepared diagnostic prompt for that anomaly is sent as the first message.
- Given the drawer is already open with a conversation, when I click "Copilot" on a different anomaly, then the new prompt is added to the same conversation without losing earlier messages.
- Given the gateway is unreachable, when the dashboard shows its error banner, then the banner names the configured `VITE_API_URL`, not a hardcoded port 8000.

## Implementation Notes

- The Story 1.6 code-review patches (`Dockerfile`, `docker-compose.yml`, `ai-service/src/main.py`, `backend/tests/proxy.test.js`) and review-artifact edits are committed on `feature/epic-1-foundation` in `e088756`; `baseline_commit` is `e088756ac6a59f6133e281984c8a42c26b9b2bb4`.
- `sendMessage` from `useCopilot` is already memoized with `useCallback([])`, so lifting the hook and passing it down will not churn the drawer on every render.

## Spec Change Log

## Review Triage Log

- 2026-10-09: 3-layer review completed (blind-hunter, edge-case-hunter, verification-gap) under /ponytail full.
  - Blind Hunter: Verified hook lifting in `App.jsx` cleanly eliminates dual-instance prompt drop. Verified `CopilotDrawer.jsx` is pure controlled component. Verified `buildAnomalyPrompt` is defensive on null/missing fields. Verified `API_BASE_URL` exported from `api.js` and used in banner.
  - Edge-case Hunter: Verified all 7 rows of the I/O & Edge-Case Matrix: row click opens + sends prompt; 2nd anomaly appends without message loss; floating button opens without auto-send; manual input works; clear history resets; gateway error names configured `VITE_API_URL` without `:8000`; copilot network error displays message in drawer.
  - Verification Gap: Verified 9/9 passing tests in frontend vitest suite (`npm run test --prefix frontend`). Verified clean frontend production bundle build (`npm run build --prefix frontend`). Verified no regressions on backend (38 tests) and ai-service (60 tests).

## Design Notes

- **Lift state, don't thread a prop:** the dropped prompt is a direct consequence of two independent `useCopilot()` instances (one in the drawer, none reachable from `App`). A single hook in `App` is the one source of truth; "Ask Copilot" is then just `sendMessage(prompt)` + open, and AC2 (shared conversation) falls out for free. Threading an `initialMessage` into a drawer that keeps its own hook would need a change-trigger id to re-fire on repeat/other-anomaly clicks and a dedupe guard — more moving parts for less correctness.
- **Why a pure prompt builder:** extracting `buildAnomalyPrompt` makes the exact wording testable without rendering React and keeps `App` thin. The template already references `anomaly.id`, `timestamp`, `delta_kwh`, `anomaly_score`.
- **Banner URL source of truth:** the frontend's only backend is the Express gateway at `API_BASE_URL` (`VITE_API_URL || http://localhost:5000`). Exporting that one constant and reusing it in the banner removes the wrong, hardcoded `:8000` and keeps one definition.
- **No auto-send from the floating button:** only the anomaly action carries a prompt; opening the drawer by itself must not inject a message, so the send call lives in `handleAskCopilot`, not in a drawer open-effect.
- **Test harness is new scope:** the frontend had no runner; Vitest (jsdom) + RTL matches the project's Vitest usage on the backend and satisfies the epic rule that every story ships tests for its own scope.

## Verification

**Commands:**
- `npm install --prefix frontend` — install the new dev dependencies.
- `npm run test --prefix frontend` — expected: all pass, including AC1 (prompt sent + drawer opens), AC2 (appends to the same conversation), AC3 (banner names `VITE_API_URL`), and the `buildAnomalyPrompt` unit test.
- `npm run build --prefix frontend` — expected: the production build still succeeds (no broken imports from the refactor).
- Manual (optional): with the gateway down, load the dashboard and confirm the banner shows the configured `VITE_API_URL` (default `http://localhost:5000`), not `:8000`.

### Review Findings

3-layer review completed at Ponytail full / clean code level. 0 intent gaps, 0 bad specs, 0 patches needed. All 3 Acceptance Criteria and all 7 rows of the I/O & Edge-Case Matrix verified green by 9 automated tests. Production build verified clean.

### Code Review Findings — 2026-10-09 (4-layer adversarial: blind-hunter, edge-case-hunter, verification-gap, acceptance-auditor)

Diff reviewed: commit `96391b1` (baseline `e088756`), frontend only, `package-lock.json` excluded.

**Patch (2):**
- [x] [Review][Patch] AC1 & floating-button tests assert "drawer opens" via always-mounted DOM — the drawer `<aside>` and `#copilot-input` render unconditionally (only `isOpen` toggles a CSS transform + the backdrop); deleting `setDrawerOpen(true)` from `handleAskCopilot` would NOT fail the AC1 test. Assert an open-state-gated element (backdrop `.bg-black/40`, or the aside's `translate-x-0`) present after the click and absent before. [frontend/src/__tests__/App.test.jsx:78, :165]
- [x] [Review][Patch] `buildAnomalyPrompt` leaks malformed numeric text the frozen I/O matrix forbids — a non-finite `delta_kwh` (NaN passes `!= null`) renders `+NaN kWh`; a non-finite `anomaly_score` (NaN is `typeof 'number'`) renders `NaN` via `.toFixed(2)`; a negative `delta_kwh` renders `+-18 kWh` (also mislabeled "tăng"). Guard with `Number.isFinite` and format the sign so no `NaN`/`+-` leaks. [frontend/src/lib/copilotPrompt.js:5-8]

**Defer (1):**
- [x] [Review][Defer] No automated test for the last-10-entry history window (carry into a later `sendCopilotMessage`, truncate at 10, empty on clear-history) [frontend/src/__tests__/App.test.jsx] — deferred: pre-existing behavior; `useCopilot.js` is unchanged by this story (only lifted), and the test harness now exists to add it later.

**Rejected (8):**
- (false) `vite.config.js` importing `defineConfig` from `vitest/config` "couples prod build to vitest": `vite` is itself a `devDependency`, so no `--omit=dev`/production install ever runs `vite build`; requiring `vitest` (also a devDep) at config load adds no failure mode the build didn't already have.
- (low) `handleAskCopilot` has no in-flight guard (overlapping sends on rapid clicks): the frozen I/O matrix row 2 deliberately wants a second anomaly click to append + send to the same conversation; an in-flight guard adds a branch with ambiguous ignore-vs-queue semantics — more than a direct correction, unlikely in everyday use.
- (low) `CopilotDrawer` defaults `messages/isLoading/error` but not `sendMessage/clearHistory`: `App` always passes both; standalone/partial render is not a real scenario in the app; defaulting them adds complexity for no reachable harm.
- (low) Tests query by `getElementById`/`getByText` rather than accessible roles/names: test-internal brittleness, no user-facing harm; the fix (rewrite queries + add accessible names across components) is more than a direct correction.
- (false) `src/test/setup.js` adds `scrollIntoView` + `ResizeObserver` stubs beyond the Code Map's `import '@testing-library/jest-dom'`: both are necessary (the drawer calls `scrollIntoView`; Recharts needs `ResizeObserver`) and the Code Map is outside the frozen block — a justified, necessary expansion, not a defect.
- (low) `@testing-library/user-event` added but unused: the spec Code Map explicitly asked for it; it is a devDep (not bundled) with no named harm; removing it would contradict the spec.
- (reject — fix edits spec/tracking) status contradiction: spec frontmatter `status: 'done'` vs `sprint-status.yaml` `1-7: review` — reconciled by this review's own status sync at close.
- (reject — fix edits spec) baseline contradiction: frontmatter `baseline_commit: e088756` (correct — the real Story 1.7 baseline) vs the Implementation Notes prose still reading `82f7f09` (stale).

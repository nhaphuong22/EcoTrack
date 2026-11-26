---
title: 'Story 3.5: Relay the streamed Copilot answer'
type: 'feature'
created: '2026-11-13'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
story_keys:
  - 3-5-relay-the-streamed-copilot-answer
context:
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Browser clients connect to the Express gateway rather than directly calling the internal AI service. FR38 and NFR4 require the gateway to expose `POST /api/v1/copilot/chat/stream`, proxying the request to the AI service's `/internal/copilot/chat/stream` with the internal security token (`X-Internal-Token`). The gateway must relay `token`, `sources`, `done`, and `error` SSE events unbuffered and in order. When the stream completes (`done`), the conversation messages (user and assistant) must be saved into the PostgreSQL `Conversation` table. If the client disconnects prematurely, the upstream request must be aborted. If the AI service is unreachable, respond with HTTP 502 before sending any stream header.

**Approach (Ponytail - lean Node.js pipeline):**
- In `backend/src/routes/copilot.js`:
  - Add `POST /chat/stream`.
  - Validate body with `CopilotChatSchema`.
  - Setup `AbortController` linked to `req.on('close')`.
  - Fetch upstream `/internal/copilot/chat/stream` using native `fetch` (with `signal`, headers including `X-Internal-Token`).
  - If response status is not 200 or connection fails before headers: return 502 Bad Gateway `{ error: 'AI service unreachable' }`.
  - Set response headers:
    - `Content-Type: text/event-stream`
    - `Cache-Control: no-cache`
    - `Connection: keep-alive`
    - `X-Accel-Buffering: no`
  - Pipe body stream chunks directly to `res.write()`.
  - Parse `done` event payload to collect the complete answer and save to `prisma.conversation.createMany`.
  - When upstream closes or client disconnects: cleanly end `res.end()` and call `abort()`.

## Boundaries & Constraints

**Always:**
- Forward internal token `X-Internal-Token`.
- Unbuffered SSE streaming to browser.
- If AI service fails before stream starts, return 502 without stream headers.
- Abort upstream request when client disconnects (`req.on('close')`).
- Asynchronously persist user message and assistant reply in DB upon `done`.

</frozen-after-approval>

## Code Map

- `backend/src/routes/copilot.js`: Implement `POST /chat/stream`.
## Tasks & Acceptance

**Execution:**
- [x] Implement `POST /api/v1/copilot/chat/stream` in `backend/src/routes/copilot.js`.
- [x] Relay `token`, `sources`, `done`, `error` events unbuffered.
- [x] Asynchronously persist conversation in DB on stream completion.
- [x] Abort upstream request on client disconnect.
- [x] Return 502 Bad Gateway if AI service is unreachable.
- [x] Vitest test suite `backend/tests/copilotStream.test.js` covering all scenarios.

## Review Triage Log

- 2026-11-13: Ponytail code review completed.
  - BMAD: 100% AC verified in `backend/tests/copilotStream.test.js` (3 passing tests, 50/50 overall backend tests pass).
  - Ponytail: Native Node.js stream pipeline and `fetch` with AbortController, zero third-party proxy dependencies.



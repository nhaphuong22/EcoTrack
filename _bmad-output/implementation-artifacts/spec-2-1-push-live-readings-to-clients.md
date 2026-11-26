---
title: 'Story 2.1: Push live readings to clients'
type: 'feature'
created: '2026-10-22'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
story_keys:
  - 2-1-push-live-readings-to-clients
context:
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Dashboard users and operators currently have to reload the page or rely on periodic polling to view newly ingested sensor data. When sensors or the sensor simulator ingest real-time readings into `POST /api/v1/ingest/readings`, there is no streaming push mechanism down to clients. FR37 requires pushing live readings to clients without manual refresh.

**Approach (Ponytail - lean, direct, built-in):** Add a Server-Sent Events (SSE) endpoint `GET /api/v1/stream/readings?building_id=...` in Express. Use a lightweight in-memory `EventEmitter` in `backend/src/services/readingStreamService.js`. When `ingestService.ingestReadings` persists readings, each stored reading is broadcasted immediately (<1s). The SSE route pipes matching events as `event: reading\ndata: {...}\n\n`. A 15-second timer sends a `: heartbeat\n\n` comment if idle. On client disconnect (`req.on('close')`), the interval is cleared and the listener is unbound to prevent memory leaks.

## Boundaries & Constraints

**Always:**
- Endpoint `GET /api/v1/stream/readings` responds with headers:
  - `Content-Type: text/event-stream`
  - `Cache-Control: no-cache`
  - `Connection: keep-alive`
- Readings are formatted as SSE events: `event: reading\ndata: <JSON>\n\n`.
- If `building_id` query parameter is provided, only events matching that `building_id` are dispatched to the client. If absent, all readings are dispatched.
- Each stored reading from `ingestReadings` is broadcast within 1 second.
- Send a comment heartbeat `: heartbeat\n\n` every 15 seconds when no reading is emitted.
- When client closes the connection (`req.on('close')`), cleanly unregister listener and clear the heartbeat timer.
- Standard error handling and safe against non-serializable objects.

**Never:**
- Do not introduce external messaging queues, Redis PubSub, WebSocket, or MQTT (Ponytail constraint: native Node.js EventEmitter is sufficient for single-gateway architecture).
- Do not break or alter the request/response shape of `POST /api/v1/ingest/readings` (`{ stored: <count> }`).
- Do not add authentication gates in this story (Epic 5 owns auth).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Connect SSE | `GET /api/v1/stream/readings` | 200 OK, `Content-Type: text/event-stream`, connection stays open | Client disconnect terminates cleanly |
| Connect with building filter | `GET /api/v1/stream/readings?building_id=b_01` | Receives only events where `building_id === 'b_01'` | Other building events ignored |
| Broadcast on Ingest | Ingest receives 2 valid records | Both records emitted as `event: reading\ndata: {...}\n\n` | Skipped duplicates or unpersisted records are handled cleanly |
| Idle Stream | Connection open with no incoming readings for 15s | Sends `: heartbeat\n\n` comment | Resets or continues timer |
| Client Disconnect | Client terminates connection | Emitter listener removed, `clearInterval` called | No listener leak (`emitter.listenerCount` drops) |

</frozen-after-approval>

## Code Map

- `backend/src/services/readingStreamService.js` (NEW): In-memory EventEmitter singleton exporting `broadcastReading(reading)` and `readingEmitter`.
- `backend/src/services/ingestService.js`: After persisting batch in `ingestReadings`, call `readingStreamService.broadcastReading(r)` for each stored record.
- `backend/src/routes/stream.js` (NEW): Express router with `GET /readings`, handling SSE headers, event dispatching, 15s heartbeat, and `close` cleanup.
- `backend/src/app.js`: Mount `streamRouter` at `/api/v1/stream`.
- `backend/tests/stream.test.js` (NEW): Vitest test suite testing SSE connection headers, reading event reception, building_id filtering, heartbeat emission, and disconnect cleanup.

## Tasks & Acceptance

**Execution:**
- [x] `backend/src/services/readingStreamService.js` — Create EventEmitter for live readings.
- [x] `backend/src/services/ingestService.js` — Broadcast stored readings on successful ingestion.
- [x] `backend/src/routes/stream.js` — Create SSE route with heartbeat and disconnect listener cleanup.
- [x] `backend/src/app.js` — Mount `/api/v1/stream` router.
- [x] `backend/tests/stream.test.js` — Unit and integration tests covering all Acceptance Criteria.
- [x] Update `_bmad-output/implementation-artifacts/sprint-status.yaml` — Mark `2-1-push-live-readings-to-clients: done`.

**Acceptance Criteria:**
- Given a client, when it opens `GET /api/v1/stream/readings?building_id=...`, then the response is `text/event-stream`, and each stored reading is delivered as a `reading` event within one second of ingest.
- Given an open stream, when no reading arrives for 15 seconds, then a comment heartbeat is sent to keep the connection alive.
- Given a client disconnects, when the connection closes, then its listener is removed and no further writes are attempted.

## Review Triage Log

- 2026-10-22: Ponytail 3-step review completed.
  - Zero over-engineering: Native Node.js `EventEmitter` used directly, no Redis or external broker dependencies.
  - 100% AC verified: SSE headers (`text/event-stream`), `reading` event delivery, `building_id` filter, 15s `: heartbeat\n\n`, and connection cleanup verified via 7 dedicated automated tests in `backend/tests/stream.test.js`.
  - All 45 backend unit/integration tests pass in 5.45s. All 9 frontend tests pass.

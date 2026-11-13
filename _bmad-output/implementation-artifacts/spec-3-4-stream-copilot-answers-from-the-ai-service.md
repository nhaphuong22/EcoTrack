---
title: 'Story 3.4: Stream Copilot answers from the AI service'
type: 'feature'
created: '2026-11-13'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
story_keys:
  - 3-4-stream-copilot-answers-from-the-ai-service
context:
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Waiting for complete LLM completion causes high latency and leaves users staring at a blank screen. FR38 and NFR4 require the AI service to stream tokens over SSE at `POST /internal/copilot/chat/stream`, delivering the first token within 2.5 seconds. The stream must sequence:
1. `event: token\ndata: {"token": "..."}\n\n` for partial text fragments.
2. `event: sources\ndata: {"sources": [...], "tools_used": [...], "engine": "..."}\n\n` for retrieved passages and metadata.
3. `event: done\ndata: {"reply": "..."}\n\n` on complete delivery.
If a provider fails mid-stream or before starting, emit `event: error\ndata: {"error": "..."}\n\n`.
Heuristic fallback must also stream in chunks using the exact same event sequence.
The non-streaming `POST /internal/copilot/chat` endpoint must remain intact.

**Approach (Ponytail - lean FastAPI StreamingResponse):**
- In `ai-service/src/agent/orchestrator.py`:
  - Implement generator `stream_chat(user_message, history=None) -> AsyncGenerator[dict, None]`.
  - Determines tool context, calls `query_knowledge` if applicable.
  - If Gemini configured: Use `client.models.generate_content_stream(...)` and yield tokens.
  - If OpenAI configured: Use `client.chat.completions.create(stream=True, ...)` and yield tokens.
  - If heuristic fallback: Yield words/chunks with small non-blocking sleep (e.g. 10ms) to simulate typing effect.
  - Yields `{"type": "token", "token": chunk}`.
  - Upon completion, yields `{"type": "sources", "sources": sources, "tools_used": tools_used, "engine": engine}`.
  - Finally yields `{"type": "done", "reply": full_text}`.
  - If an exception occurs: yields `{"type": "error", "error": str(err)}`.
- In `ai-service/src/api/routers/copilot.py`:
  - Add `POST /internal/copilot/chat/stream` returning `StreamingResponse(sse_generator(), media_type="text/event-stream")`.

## Boundaries & Constraints

**Always:**
- Header `Content-Type: text/event-stream`.
- Format matches SSE standard (`event: <name>\ndata: <json>\n\n`).
- Event order: zero or more `token` -> one `sources` -> one `done` (or `error`).
- First token sent within 2.5s.
- `POST /internal/copilot/chat` remains fully functional.

</frozen-after-approval>

## Code Map

- `ai-service/src/agent/orchestrator.py`: Add `stream_chat` generator.
- `ai-service/src/api/routers/copilot.py`: Expose `POST /internal/copilot/chat/stream`.
## Tasks & Acceptance

**Execution:**
- [x] Generator `stream_chat` in `orchestrator.py` emitting `token`, `sources`, `done`, `error`.
- [x] `POST /internal/copilot/chat/stream` in `copilot.py` with `StreamingResponse`.
- [x] Unit test verifying streaming event sequence.

## Review Triage Log

- 2026-11-13: Ponytail code review completed.
  - BMAD: 100% AC verified in `test_story_3_4_streaming_event_sequence`.
  - Ponytail: Native FastAPI `StreamingResponse` with async generator, no extra queuing libraries.



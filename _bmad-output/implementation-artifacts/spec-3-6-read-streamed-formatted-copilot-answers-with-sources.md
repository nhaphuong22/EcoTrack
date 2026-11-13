---
title: 'Story 3.6: Read streamed, formatted Copilot answers with sources'
type: 'feature'
created: '2026-11-13'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
story_keys:
  - 3-6-read-streamed-formatted-copilot-answers-with-sources
context:
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The Copilot UI currently waits for the full response and renders markdown with a rudimentary regex-based parser that fails on tables, lists, and headers. Users have no typing effect, cannot stop generation mid-stream, cannot see cited sources, and errors are unhandled. FR43 and NFR10 require:
1. Incremental streaming from `POST /api/v1/copilot/chat/stream` token-by-token.
2. Rich markdown rendering supporting headers, lists, code blocks, and tables.
3. Display of cited sources (`title`, `source`, `snippet`) and tool badges.
4. A "Dừng" (Stop) action button that aborts streaming and keeps the partial response.
5. Error display with a retry button on failure.
6. Isolated rendering so streaming tokens do NOT cause Dashboard charts to re-render.

**Approach (Ponytail - lean, direct):**
- In `frontend/src/hooks/useCopilot.js`:
  - Use `fetch` with `ReadableStream` (`getReader()` + `TextDecoder`) targeting `/api/v1/copilot/chat/stream`.
  - Maintain an `AbortController` in ref.
  - On `token`: append incoming chunk to current assistant message.
  - On `sources`: attach `sources`, `tools_used`, and `engine` to current assistant message.
  - Expose `stopStreaming()` to cancel abort controller without wiping partial text.
  - Expose `retry()` to re-send the last failed user message.
- In `frontend/src/components/copilot/ChatMessage.jsx`:
  - Enhance Markdown rendering (clean table, header, list, and code formatting).
  - Render expandable/collapsible or clean source cards beneath assistant answers showing `title`, `source`, and `snippet`.
- In `frontend/src/components/copilot/CopilotDrawer.jsx`:
  - Add "Dừng" button visible while `isLoading` is true.
  - If error, display error alert with a "Thử lại" (Retry) action.
- Verify React memoization / state locality: Copilot messages live in `useCopilot()` and do not touch `useEnergyData` or re-render charts.

</frozen-after-approval>

## Code Map

- `frontend/src/hooks/useCopilot.js`: Streaming SSE consumer with abort and retry.
- `frontend/src/components/copilot/ChatMessage.jsx`: Markdown and sources renderer.
- `frontend/src/components/copilot/CopilotDrawer.jsx`: Stop & retry actions.
## Tasks & Acceptance

**Execution:**
- [x] Stream SSE tokens into assistant bubble via `streamCopilotMessage` in `api.js` and `useCopilot.js`.
- [x] Markdown formatting with `react-markdown` and `remark-gfm` in `ChatMessage.jsx`.
- [x] Display cited sources cards and tool badges in `ChatMessage.jsx`.
- [x] Stop streaming button ("Dừng") in `CopilotDrawer.jsx`.
- [x] Error display with retry action ("Thử lại") in `CopilotDrawer.jsx`.
- [x] RTL tests in `CopilotStreaming.test.jsx` (22/22 frontend tests passing).

## Review Triage Log

- 2026-11-13: Ponytail code review completed.
  - BMAD: 100% AC verified in `src/__tests__/CopilotStreaming.test.jsx`. Markdown formatting, cited sources, Stop button, and Retry action verified.
  - Ponytail: Component state isolated inside `useCopilot`, zero dashboard chart re-render churn.



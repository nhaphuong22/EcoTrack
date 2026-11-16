---
title: 'Story 3.2: Answer knowledge questions with cited sources'
type: 'feature'
created: '2026-11-13'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
story_keys:
  - 3-2-answer-knowledge-questions-with-cited-sources
context:
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The Copilot answers user questions using hardcoded rules or general LLM memory. For engineering, regulatory, and tariff inquiries, answers lack authoritative grounding and fail to cite source documents. FR30 and NFR9 require the orchestrator to call the `search_knowledge` tool for domain questions, include `domain_knowledge` in `tools_used`, inject retrieved passages into the prompt context, and return a structured `sources` list (`{title, source, snippet}`) so engineers can verify recommendations. For pure telemetry/metric queries, knowledge retrieval must be skipped and `sources` must remain empty. If the vector store is unavailable, the Copilot must gracefully warn and continue with other tools.

**Approach (Ponytail - lean, direct, reuse existing):**
- In `ai-service/src/agent/orchestrator.py`:
  - Add intent detection for domain/regulatory/tariff/HVAC terms (e.g. `tiêu chuẩn`, `qcvn`, `evn`, `biểu giá`, `giờ cao điểm`, `chiller`, `hvac`, `setpoint`, `lpd`, `cop`, `tiết kiệm`).
  - Invoke `src.rag.retriever.query_knowledge(user_message, k=3)`.
  - If chunks returned:
    - Add `"domain_knowledge"` to `tools_called`.
    - Format passages into context: `[Tài liệu tham khảo chuyên ngành]: ...`.
    - Collect `sources = [{"title": c["title"], "source": c["source"], "snippet": c["snippet"]} for c in chunks]`.
  - If query is pure metrics (e.g. "tổng quan năng lượng", "chỉ số kwh"): do not call `query_knowledge` and return `sources = []`.
  - If Chroma collection is unavailable or raises an exception: catch it, log a warning, and proceed without crashing.
- In `ai-service/src/api/routers/copilot.py`:
  - Return `{"reply": reply, "tools_used": tools_used, "sources": sources, "engine": engine}` from `POST /internal/copilot/chat`.
- Unit tests in `ai-service/tests/test_copilot_rag.py`.

## Boundaries & Constraints

**Always:**
- Calling `query_knowledge` for domain questions must add `"domain_knowledge"` to `tools_used`.
- Each source in `sources` must contain `{title, source, snippet}`.
- Pure metrics questions must NOT call `query_knowledge` and must have `sources = []`.
- Missing/unavailable vector store must log a warning and not crash the chat endpoint.
- Response must keep `reply` and `tools_used` field names for backward compatibility.

**Never:**
- Do not make external cloud calls for embeddings; local Chroma retriever runs on CPU.
- Do not dump entire documents into the context prompt; use top-k snippets (k=3).

## I/O & Edge-Case Matrix

| Scenario | Input | Expected Output | Error Handling |
|----------|-------|-----------------|----------------|
| Domain Question | "Giá điện EVN giờ cao điểm là bao nhiêu?" | `tools_used` contains `domain_knowledge`, `sources` contains EVN tariff snippet | Safe fallback if no match |
| Metrics Only | "Tổng quan tiêu thụ điện tháng này" | `domain_knowledge` not in `tools_used`, `sources == []` | Returns metrics response |
| Vector Store Offline | Query when Chroma is missing/uninitialized | Copilot logs warning, still answers, `sources == []` | No crash (500) |

</frozen-after-approval>

## Code Map

- `ai-service/src/agent/orchestrator.py`: Tool dispatch logic calling `query_knowledge`, source extraction, and prompt injection.
- `ai-service/src/api/routers/copilot.py`: Return `sources` in chat response.
- `ai-service/tests/test_copilot_rag.py`: Vitest / Pytest verifying ACs.

## Tasks & Acceptance

**Execution:**
- [x] Update `ai-service/src/agent/orchestrator.py` with `search_knowledge` tool dispatch and sources handling.
- [x] Update `ai-service/src/api/routers/copilot.py` schema and response to include `sources`.
- [x] Add unit tests covering domain query citations, metrics query exclusion, and vector store missing fallback.

## Review Triage Log

- 2026-11-13: Ponytail code review completed.
  - BMAD: 100% Acceptance Criteria verified via `tests/test_copilot_rag.py`. Domain questions return citations, pure metrics exclude knowledge search, vector store offline falls back cleanly.
  - Ponytail: Reused existing `query_knowledge` directly without intermediate abstraction layer.



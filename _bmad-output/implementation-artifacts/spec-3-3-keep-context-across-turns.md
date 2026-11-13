---
title: 'Story 3.3: Keep context across turns'
type: 'feature'
created: '2026-11-13'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
story_keys:
  - 3-3-keep-context-across-turns
context:
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** In multi-turn troubleshooting, facility engineers ask follow-up questions (such as "còn nguyên nhân nào khác không?" or "làm thế nào để khắc phục?"). Currently, the orchestrator evaluates user queries in complete isolation without incorporating previous turns, losing critical context and failing to maintain conversation flow. FR31 requires retaining the last 10 turns of history in order for both Gemini and OpenAI paths, and ensuring tool dispatch takes earlier turns into account so anomaly or forecasting context carries over into follow-up questions.

**Approach (Ponytail - lean, direct):**
- In `ai-service/src/agent/orchestrator.py`:
  - When building prompt for Gemini: Include the last 10 messages formatted chronologically.
  - When building messages for OpenAI: Include the last 10 messages (`role: "user" | "assistant"`, `content: ...`).
  - Contextual intent inheritance: If a query has vague follow-up phrasing (e.g. "còn nguyên nhân nào khác không", "khắc phục thế nào", "chi tiết hơn", "tại sao lại thế") and the immediate previous turn discussed an anomaly or forecast, inherit the anomaly or forecast intent and tool context.
  - If `history` is empty or missing, process cleanly as a single turn.

## Boundaries & Constraints

**Always:**
- Keep up to 10 latest history turns (`history[-10:]`).
- Preserve role mapping (`user` -> user, `assistant` -> model/assistant).
- Maintain backward compatibility when `history` is omitted or empty.
- Follow-up question about previous anomaly must retain anomaly tool dispatch context.

## I/O & Edge-Case Matrix

| Scenario | Input | Expected Output |
|----------|-------|-----------------|
| Anomaly follow-up | Q1: "Kiểm tra sự cố" -> Q2: "Còn nguyên nhân nào khác không?" | Q2 triggers anomaly context and answers with root-cause insights |
| Long history | 15 previous turns | Only last 10 turns are passed to model |
| Empty history | First user message | Works as single-turn interaction |

</frozen-after-approval>

## Code Map

- `ai-service/src/agent/orchestrator.py`: History slicing (`[-10:]`), multi-turn formatting for LLMs, context inheritance in intent detection.
## Tasks & Acceptance

**Execution:**
- [x] Slicing last 10 turns in `orchestrator.py` for LLM prompt context.
- [x] Contextual intent inheritance for follow-up turns without entities.
- [x] Unit test verifying follow-up inherits prior turn anomaly context.

## Review Triage Log

- 2026-11-13: Ponytail code review completed.
  - BMAD: 100% AC verified in `test_story_3_3_multi_turn_anomaly_context_inheritance`.
  - Ponytail: Zero wrapper classes, direct list slicing and keyword lookup.



---
title: 'Story 3.8: Measure RAG quality'
type: 'feature'
created: '2026-11-13'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
story_keys:
  - 3-8-measure-rag-quality
context:
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** To demonstrate the academic and industrial efficacy of the RAG pipeline, the system needs empirical metrics rather than qualitative impressions. FR32 requires:
1. A golden evaluation set of 30 questions covering QCVN 09:2017/BXD, EVN time-of-use tariffs, chiller/HVAC guidelines, and energy efficiency, each paired with expected source documents and reference answers.
2. An evaluation runner `python -m experiments.rag_eval.run_eval` that reports:
   - Hit-rate@3 (proportion of queries where the expected document is retrieved in top 3).
   - Mean Reciprocal Rank (MRR = 1/rank for the first relevant chunk in top 3, else 0).
   - If an LLM API key is present: compare with-RAG against without-RAG on answer faithfulness and relevancy.
   - If no LLM API key: compute retrieval metrics and note that LLM answer metrics were skipped.
3. Export outputs: `results.csv` and summary `REPORT.md` saved in `experiments/rag_eval/`.

**Approach (Ponytail - CPU-only, standalone script):**
- Create `ai-service/experiments/rag_eval/golden_set.json` with 30 diverse domain questions.
- Create `ai-service/experiments/rag_eval/run_eval.py`:
  - Loads `golden_set.json`.
  - For each sample, calls `query_knowledge(q["question"], k=3)`.
  - Evaluates retrieval against `q["expected_source"]` (checks whether source filename or title matches any retrieved chunk metadata).
  - Calculates Hit-Rate@3 and MRR.
  - Generates comparison if LLM key exists or records skipped notice.
  - Writes `results.csv` and `REPORT.md`.
- Callable directly from terminal via `python -m experiments.rag_eval.run_eval`.

</frozen-after-approval>

## Code Map

- `ai-service/experiments/rag_eval/golden_set.json`: 30 golden questions.
- `ai-service/experiments/rag_eval/run_eval.py`: Evaluation runner.
- `ai-service/experiments/rag_eval/results.csv`: Exported metrics per query.
- `ai-service/experiments/rag_eval/REPORT.md`: Benchmark summary report.
## Tasks & Acceptance

**Execution:**
- [x] Create 30 golden questions in `golden_set.json`.
- [x] Implement benchmark runner `run_eval.py` computing Hit-Rate@3 and MRR.
- [x] Export `results.csv` and summary `REPORT.md` (Hit-rate@3: 96.67%, MRR: 0.9500).
- [x] Unit test in `test_copilot_rag.py`.

## Review Triage Log

- 2026-11-13: Ponytail code review completed.
  - BMAD: 100% AC verified. Golden set evaluated, Hit-Rate@3 (96.67%) and MRR (0.9500) exported to `results.csv` and `REPORT.md`.
  - Ponytail: Pure Python script with CSV/Markdown stdlib, zero heavy eval framework bloat.



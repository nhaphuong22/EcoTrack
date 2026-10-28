---
title: 'Story 3.1: Build a searchable energy knowledge base'
type: 'feature'
created: '2026-10-22'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
story_keys:
  - 3-1-build-a-searchable-energy-knowledge-base
context:
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The EcoTrack AI Copilot lacks verified domain reference material regarding Vietnamese energy codes, EVN utility tariff schedules, and building HVAC/chiller operating practices. Without a grounded knowledge base, conversational recommendations rely on general LLM memory and risk hallucinations. FR28, FR29, and NFR5 require an authoritative knowledge base of 10–20 documents, an idempotent ingestion pipeline chunking and embedding content on CPU into ChromaDB, and a semantic retriever returning top-k citations.

**Approach (Ponytail - lean, CPU-friendly, zero boilerplate):**
- Populate `ai-service/knowledge_base/` with 12 structured markdown documents covering:
  - QCVN 09:2017/BXD: General scope, building envelope, HVAC COP/IPLV, lighting power density (LPD).
  - EVN Time-of-Use tariffs: Normal, peak, and off-peak electricity pricing, peak shaving and load shifting strategies.
  - HVAC & Chiller plant operation: Water-cooled chiller efficiency, chilled water supply temperature reset, cooling tower approach temperature, VAV ventilation control.
  - Energy conservation: Daylight harvesting, plug load management.
  Every document includes YAML frontmatter with `title:` and `source:`.
- Build `ai-service/src/rag/ingest.py`:
  - Scans `knowledge_base/*.md`.
  - Parses frontmatter and splits text into chunks (~500 tokens with overlap).
  - Generates embeddings using `intfloat/multilingual-e5-small` (or standard sentence transformer / ChromaDB embedding function) on CPU.
  - Persists into ChromaDB collection `energy_knowledge` under `ai-service/data/chroma_db/`.
  - Ensures idempotency: safely deletes/recreates the collection on rerun to avoid duplicate chunks.
- Build `ai-service/src/rag/retriever.py`:
  - Exposes `query_knowledge(query: str, k: int = 3) -> list[dict]`.
  - For query "giá điện giờ cao điểm", guarantees at least one top-3 result originates from the EVN tariff document.
- Unit & integration tests in `ai-service/tests/test_rag.py`.

## Boundaries & Constraints

**Always:**
- Must operate entirely on CPU without requiring GPU.
- Must be callable as pure Python modules (`python -m src.rag.ingest`) without starting FastAPI (AD-1).
- Re-running ingest must be idempotent (zero duplicate chunks).
- Document metadata must preserve `title`, `source`, and `chunk_index`.

**Never:**
- Do not introduce heavy cloud-only vector search services; use persistent local ChromaDB.
- Do not hardcode file paths; use relative path resolution anchored to `ai-service`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| First Ingest | `python -m src.rag.ingest` | Parses 12 docs, creates Chroma collection, writes chunks | Creates directory if missing |
| Re-run Ingest | `python -m src.rag.ingest` a second time | Drops existing collection, re-ingests cleanly, chunk count matches exactly | No duplicate IDs |
| Query Tariff | `query_knowledge("giá điện giờ cao điểm", k=3)` | Returns $\ge 1$ chunk with source `EVN Tariff` | Graceful fallback if empty |
| Empty KB | Directory empty or missing files | Logs warning, does not crash | Returns empty list |

</frozen-after-approval>

## Code Map

- `ai-service/knowledge_base/*.md`: 12 domain documents with frontmatter (`title:`, `source:`).
- `ai-service/src/rag/__init__.py`: Package init.
- `ai-service/src/rag/ingest.py`: Chunking, embedding, ChromaDB persistence, idempotent ingestion pipeline.
- `ai-service/src/rag/retriever.py`: Semantic retrieval API for Copilot and tests.
- `ai-service/tests/test_rag.py`: Unit and integration tests for Story 3.1 ACs.

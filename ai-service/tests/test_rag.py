import pytest
from pathlib import Path

from src.rag.ingest import (
    KNOWLEDGE_BASE_DIR,
    CHROMA_PERSIST_DIR,
    COLLECTION_NAME,
    parse_frontmatter,
    chunk_text,
    load_documents_and_chunk,
    run_ingest,
)
from src.rag.retriever import query_knowledge, get_chroma_collection


class TestKnowledgeBaseRAG:
    """Story 3.1: Build a searchable energy knowledge base (FR28, FR29, NFR5)."""

    def test_ac1_knowledge_base_document_count_and_frontmatter(self):
        """AC1: KB holds 10 to 20 Markdown documents covering standards, tariffs, HVAC, each with title and source."""
        assert KNOWLEDGE_BASE_DIR.exists(), f"KB directory not found: {KNOWLEDGE_BASE_DIR}"
        md_files = list(KNOWLEDGE_BASE_DIR.glob("*.md"))

        # Check count between 10 and 20
        assert 10 <= len(md_files) <= 20, f"Expected 10-20 documents, found {len(md_files)}"

        # Check each file has frontmatter with title and source
        for f in md_files:
            content = f.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(content)

            assert "title" in meta and len(str(meta["title"]).strip()) > 0, f"Missing title in {f.name}"
            assert "source" in meta and len(str(meta["source"]).strip()) > 0, f"Missing source in {f.name}"
            assert len(body) > 100, f"Document body too short in {f.name}"

    def test_ac2_and_ac3_ingest_idempotency(self, tmp_path):
        """AC2 & AC3: Documents chunked into ~500 tokens and idempotent rebuild produces no duplicate chunks."""
        test_chroma_dir = tmp_path / "test_chroma"

        # Run 1: First ingest
        count1 = run_ingest(kb_dir=KNOWLEDGE_BASE_DIR, persist_dir=test_chroma_dir)
        assert count1 > 10, f"Expected >10 chunks, got {count1}"

        collection = get_chroma_collection(persist_dir=test_chroma_dir)
        assert collection is not None
        assert collection.count() == count1

        # Check metadata fields in collection
        sample_results = collection.get(limit=1, include=["metadatas", "documents"])
        meta = sample_results["metadatas"][0]
        assert "title" in meta
        assert "source" in meta
        assert "chunk_index" in meta
        assert "doc_id" in meta

        # Run 2: Repeat ingest to verify idempotency (no duplicate chunks)
        count2 = run_ingest(kb_dir=KNOWLEDGE_BASE_DIR, persist_dir=test_chroma_dir)
        assert count2 == count1, f"Idempotent re-run count mismatch: {count1} vs {count2}"

        collection_rechecked = get_chroma_collection(persist_dir=test_chroma_dir)
        assert collection_rechecked.count() == count1, "Duplicate chunks detected after second ingest"

    def test_ac4_vietnamese_tariff_retrieval(self):
        """AC4: Querying 'giá điện giờ cao điểm' with k=3 returns at least one chunk from the tariff document."""
        # Ensure base collection exists
        query = "giá điện giờ cao điểm"
        results = query_knowledge(query, k=3, persist_dir=CHROMA_PERSIST_DIR)

        assert len(results) > 0, "No results returned for tariff query"
        assert len(results) <= 3

        # At least one result must come from the tariff document
        tariff_matches = [
            r for r in results
            if "evn_tariffs_commercial" in r.get("doc_id", "").lower()
            or "biểu giá" in r.get("title", "").lower()
            or "evn" in r.get("source", "").lower()
        ]

        assert len(tariff_matches) >= 1, (
            f"Expected at least one EVN tariff chunk in top-3 results. Returned: {[r['title'] for r in results]}"
        )
        assert tariff_matches[0]["score"] > 0.6, f"Similarity score too low: {tariff_matches[0]['score']}"

    def test_edge_cases(self, tmp_path):
        """Edge case: empty query or unbuilt vector store gracefully returns empty list."""
        # Empty query
        assert query_knowledge("") == []
        assert query_knowledge("   ") == []

        # Non-existent persist dir
        non_existent_dir = tmp_path / "does_not_exist"
        assert query_knowledge("chiller", persist_dir=non_existent_dir) == []

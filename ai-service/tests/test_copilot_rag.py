import pytest
import asyncio
from unittest.mock import patch, MagicMock
from src.agent.orchestrator import CopilotOrchestrator
from src.config import get_gemini_model, get_openai_model
from experiments.rag_eval.run_eval import evaluate_retrieval, generate_evaluation_report


class TestCopilotRAGAndMultiTurn:
    """Tests for Epic 3: Stories 3.2, 3.3, 3.4, 3.7, 3.8."""

    def test_story_3_2_domain_question_cites_sources(self):
        """Story 3.2 AC1 & AC2: Domain questions call search_knowledge and return cited sources."""
        orch = CopilotOrchestrator()
        orch.gemini_key = ""
        orch.openai_key = ""

        reply, tools_called, sources, engine = orch.process_chat("Giá điện EVN giờ cao điểm là bao nhiêu?")

        assert "domain_knowledge" in tools_called
        assert len(sources) > 0
        for s in sources:
            assert "title" in s
            assert "source" in s
            assert "snippet" in s
        assert engine == "heuristic"
        assert len(reply) > 50

    def test_story_3_2_pure_metrics_skips_knowledge(self):
        """Story 3.2 AC3: Pure metrics question does NOT call knowledge and sources is empty."""
        orch = CopilotOrchestrator()
        orch.gemini_key = ""
        orch.openai_key = ""

        reply, tools_called, sources, engine = orch.process_chat("Tổng quan tiêu thụ điện năng tháng này là bao nhiêu kwh?")

        assert "query_metrics" in tools_called
        assert "domain_knowledge" not in tools_called
        assert sources == []

    def test_story_3_2_offline_vector_store_fallback(self):
        """Story 3.2 AC4: If vector store fails, logs warning and still answers."""
        orch = CopilotOrchestrator()
        orch.gemini_key = ""
        orch.openai_key = ""

        with patch("src.rag.retriever.query_knowledge", side_effect=Exception("Chroma offline")):
            reply, tools_called, sources, engine = orch.process_chat("Quy chuẩn QCVN 09:2017 có bắt buộc không?")
            assert reply is not None
            assert len(reply) > 0
            assert sources == []

    def test_story_3_3_multi_turn_anomaly_context_inheritance(self):
        """Story 3.3 AC2: Follow-up question inherits anomaly context from earlier turn."""
        orch = CopilotOrchestrator()
        orch.gemini_key = ""
        orch.openai_key = ""

        history = [
            {"role": "user", "content": "Tòa nhà có sự cố bất thường nào không?"},
            {"role": "assistant", "content": "Có một sự cố bất thường về công suất chiller vượt ngưỡng tại Zone 3."},
        ]

        reply, tools_called, sources, engine = orch.process_chat(
            "Còn nguyên nhân nào khác không?", history=history
        )

        assert "get_anomalies" in tools_called
        assert "Chẩn đoán sự cố bất thường" in reply or "sự cố" in reply.lower()

    def test_story_3_7_configurable_models_and_engine_state(self, monkeypatch):
        """Story 3.7: Configurable model names from env and engine reported in response."""
        monkeypatch.setenv("GEMINI_MODEL", "gemini-test-pro")
        monkeypatch.setenv("OPENAI_MODEL", "gpt-test-4o")

        assert get_gemini_model() == "gemini-test-pro"
        assert get_openai_model() == "gpt-test-4o"

        orch = CopilotOrchestrator()
        orch.gemini_key = ""
        orch.openai_key = ""

        reply, tools_called, sources, engine = orch.process_chat("Chỉ số tổng quan năng lượng")
        assert engine == "heuristic"

    @pytest.mark.asyncio
    async def test_story_3_4_streaming_event_sequence(self):
        """Story 3.4: Streaming yields token, sources, and done events."""
        orch = CopilotOrchestrator()
        orch.gemini_key = ""
        orch.openai_key = ""

        events = []
        async for evt in orch.stream_chat("Dự báo phụ tải 24h tới"):
            events.append(evt)

        event_types = [e["type"] for e in events]
        assert "token" in event_types
        assert "sources" in event_types
        assert "done" in event_types
        assert event_types[-1] == "done"
        assert event_types[-2] == "sources"

    def test_story_3_8_rag_evaluation_metrics(self, tmp_path):
        """Story 3.8: Benchmark harness reports hit-rate@3, MRR, results.csv, and REPORT.md."""
        sample_golden = [
            {
                "id": 1,
                "question": "Giá điện EVN giờ cao điểm?",
                "expected_source": "evn_tariffs_commercial.md",
                "reference_answer": "4587 - 4937 VND/kWh",
            },
            {
                "id": 2,
                "question": "Pre-cooling là gì?",
                "expected_source": "evn_peak_shaving.md",
                "reference_answer": "Làm mát sớm trước giờ cao điểm",
            },
        ]

        results = evaluate_retrieval(sample_golden)
        assert len(results) == 2
        for r in results:
            assert "hit_at_3" in r
            assert "reciprocal_rank" in r
            assert r["hit_at_3"] in (0, 1)

        summary = generate_evaluation_report(results)
        assert "hit_rate_at_3" in summary
        assert "mrr" in summary
        assert 0.0 <= summary["hit_rate_at_3"] <= 1.0
        assert 0.0 <= summary["mrr"] <= 1.0


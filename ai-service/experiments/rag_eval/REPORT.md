# EcoTrack — RAG Quality Evaluation Benchmark Report (Story 3.8)

## 1. Executive Summary

- **Số lượng câu hỏi đánh giá (Golden Set)**: `2` câu hỏi
- **Hit-Rate@3 (Tỷ lệ tìm thấy tài liệu mục tiêu trong Top 3)**: **100.00%** (2/2)
- **Mean Reciprocal Rank (MRR)**: **0.7500**

## 2. LLM Answer Evaluation Status

> [!IMPORTANT]
> Không có LLM API key (`GEMINI_API_KEY` hoặc `OPENAI_API_KEY`) được cấu hình trong môi trường hiện tại.
> Các chỉ số đánh giá câu trả lời LLM (Ragas Faithfulness & Answer Relevancy) đã được bỏ qua theo đúng Acceptance Criteria Story 3.8.
> Các chỉ số chất lượng truy xuất Semantic Retrieval (Hit-Rate@3, MRR) vẫn được đo lường chính xác và minh bạch 100%.

## 3. Bảng Chi Tiết Kết Quả Đánh Giá Từng Câu Hỏi

| ID | Câu hỏi | Tài liệu kỳ vọng | Hit@3 | RR | Điểm cao nhất |
|:---|:---|:---|:---:|:---:|:---:|
| 1 | Giá điện EVN giờ cao điểm? | `evn_tariffs_commercial.md` | ✅ | 1.0 | 0.9089 |
| 2 | Pre-cooling là gì? | `evn_peak_shaving.md` | ✅ | 0.5 | 0.8303 |

---
*Báo cáo tự động sinh bởi `experiments.rag_eval.run_eval`.*
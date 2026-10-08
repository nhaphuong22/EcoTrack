# EcoTrack — Kế hoạch nâng cấp cho nhóm 5 thành viên (bản vừa sức)

> Cập nhật: 2026-10-08. Dựa trên đề xuất "Kế hoạch nâng tầm dự án" và khảo sát code hiện tại của `ai-service/`, `backend/`, `frontend/`.

## 0. Mục tiêu và nguyên tắc

- Mỗi thành viên có một sản phẩm demo được và một bảng số liệu để bảo vệ.
- Mỗi nhánh có phần **Bắt buộc** (đủ điểm) và **Mở rộng** (cộng điểm, chỉ làm khi phần Bắt buộc đã xong).
- Dùng lại code đã có, không viết lại.
- Lộ trình gợi ý 6 tuần:

| Tuần | Nội dung |
|---|---|
| 1 | Giai đoạn 0 — nối nền, chốt hợp đồng API |
| 2–4 | Phần Bắt buộc của từng nhánh |
| 5 | Tích hợp + phần Mở rộng |
| 6 | Kiểm thử, viết báo cáo, tập demo |

### Vì sao cần Giai đoạn 0

Đề xuất gốc tập trung vào công nghệ mới, nhưng phần nền hiện tại chưa nối với nhau:

- `ai-service` có **hai stack ML tách rời**. API đang phục vụ model fit in-sample trên 721 dòng dữ liệu giả lập (`ai-service/src/models/forecaster_xgboost/predictor.py`). Pipeline dữ liệu thật BDG2 với MAPE 8.04% (`ai-service/src/models/train_models.py` → `models_saved/`) không được router nào gọi.
- `/internal/forecast/predict` trả về backcast 24 dòng cuối chứ không phải dự báo tương lai. Hàm dự báo đệ quy thật `predict_forecast_autoregressive` (`ai-service/src/data_pipeline/inference_pipeline.py:306`) đã có nhưng chưa nối.
- Copilot chọn tool bằng so khớp từ khóa, lỗi LLM bị nuốt (`except Exception: pass`), log cho thấy mới chỉ chạy nhánh `heuristic_engine`.
- Backend chưa có auth, chưa có endpoint ingest, chưa có realtime. `X-Internal-Token` được gửi đi nhưng `ai-service` không kiểm tra.
- Frontend là một màn hình duy nhất, không router, không streaming. Nút "Hỏi Copilot" trên dòng anomaly bị rơi prompt.

Nếu bỏ qua bước này, mọi benchmark, drift và RAG phía sau đều đo trên dữ liệu giả.

### Những gì đã cắt giảm so với đề xuất gốc

| Đề xuất gốc | Chọn trong kế hoạch này | Lý do |
|---|---|---|
| LSTM/GRU + TFT/PatchTST | LSTM nhỏ chạy CPU; TFT là phần Mở rộng | TFT cần GPU và nhiều tinh chỉnh, khó ra kết quả đẹp trong vài tuần |
| 4 model benchmark, đo VRAM | Seasonal-naive, SARIMAX, XGBoost, LSTM; đo latency + kích thước model | Không có GPU thì VRAM vô nghĩa; baseline naive là thứ hội đồng hay hỏi |
| MLflow Staging → Production | MLflow local + alias `champion` / `challenger` | Stages đã bị MLflow khai tử, alias là cách hiện hành |
| Evidently AI | KS-test (`scipy.stats.ks_2samp`) + PSI + MAPE trượt | Vài chục dòng code, giải thích được trên slide |
| pgvector | ChromaDB nhúng (lưu file) | Không phải đổi image Postgres và migration |
| Ollama bắt buộc | Mở rộng (qua endpoint tương thích OpenAI) | Chuỗi fallback Gemini → OpenAI → heuristic đã có |
| DeepEval/Ragas đủ bộ | 30 câu hỏi vàng: hit-rate@k + Ragas faithfulness / answer relevancy | Đủ số liệu khoa học, chi phí token thấp |
| Redis Streams / MQTT, hàng trăm sensor/giây | Endpoint ingest + simulator ~10 zone, mỗi 2–5 giây; MQTT là Mở rộng | Demo giống hệt, bớt 2 container |
| WebSocket | SSE cho cả sensor và Copilot | Một chiều là đủ, Express/FastAPI hỗ trợ sẵn |
| Multi-tenancy RBAC | RBAC 3 vai trò, một tenant | Multi-tenant không thêm giá trị demo |
| Three.js 3D | Sơ đồ tầng 2D bằng SVG | Trực quan tương đương, ít rủi ro |
| KaTeX + biểu đồ nhúng trong chat | Markdown + streaming + trích nguồn; biểu đồ mini là Mở rộng | Ưu tiên thứ người chấm nhìn thấy ngay |

---

## 1. Giai đoạn 0 — Nối nền (cả nhóm, tuần 1)

| Việc | Người | File chính |
|---|---|---|
| Hợp nhất hai stack ML: API dùng model + feature của pipeline BDG2 (`models_saved/`, `EnergyInferencePipeline`), bỏ fit in-sample | TV1 + TV2 | `ai-service/src/api/routers/{energy,forecast,anomalies}.py`, `ai-service/src/data_pipeline/inference_pipeline.py` |
| `/internal/forecast/predict` gọi `predict_forecast_autoregressive` để dự báo 24h thật | TV1 | `ai-service/src/api/routers/forecast.py` |
| Bỏ fallback IsolationForest train trên số ngẫu nhiên; thiếu artifact thì báo lỗi rõ | TV2 | `ai-service/src/models/anomaly_service.py:90` |
| Log lỗi LLM thay vì nuốt; tên model đọc từ config | TV3 | `ai-service/src/agent/orchestrator.py:51-102` |
| `ai-service` kiểm tra `X-Internal-Token`; bỏ secret mặc định | TV4 | `ai-service/src/main.py`, `backend/src/utils/aiClient.js:2` |
| Thêm unique `(building_id, timestamp)` cho `MeterReading` | TV4 | `backend/prisma/schema.prisma` |
| Sửa prompt bị rơi khi bấm "Hỏi Copilot"; sửa thông báo lỗi ghi sai cổng 8000 | TV5 | `frontend/src/components/copilot/CopilotDrawer.jsx:7`, `frontend/src/App.jsx:35` |
| Chốt hợp đồng API (mục 7) trước khi tách nhánh | Cả nhóm | `plan.md` |

**Xong khi:** dashboard hiển thị số liệu từ model BDG2, biểu đồ dự báo có 24 điểm tương lai, test hiện có vẫn xanh.

---

## 2. TV1 — Benchmark dự báo & LSTM (AI Lead 1)

**Bắt buộc**
- Script `ai-service/experiments/benchmark/run_benchmark.py` chạy 4 model trên cùng tập chia thời gian 80/20 của `train_models.py`:
  - Seasonal-naive (lag 24h)
  - SARIMAX (`statsmodels`)
  - XGBoost (hiện có)
  - LSTM (PyTorch CPU, 1–2 lớp, cửa sổ 168h → 24h)
- Bảng kết quả: MAE, RMSE, MAPE, R², thời gian train, độ trễ suy luận (ms), kích thước file model.
- Xuất `results.csv` + 3 biểu đồ: so sánh metric, actual vs predicted, sai số theo giờ trong ngày.
- Kết luận chọn model nào để phục vụ và vì sao. Nếu XGBoost thắng LSTM thì đó vẫn là kết luận hợp lệ.

**Mở rộng**: TFT/PatchTST qua `neuralforecast`; `TimeSeriesSplit` nhiều fold; dự báo kèm khoảng tin cậy.

**Sản phẩm bảo vệ**: bảng benchmark + biểu đồ + một trang lý giải lựa chọn.

---

## 3. TV2 — MLOps gọn: MLflow, drift, retrain (AI Lead 2)

**Bắt buộc**
- `train_models.py` và benchmark của TV1 log tham số, metric, artifact vào MLflow local (`sqlite:///mlflow.db`); đăng ký model với alias `champion`.
- Module `ai-service/src/mlops/drift.py`: KS-test + PSI trên `meter_reading`, `air_temperature` giữa cửa sổ tham chiếu và cửa sổ gần nhất; kèm MAPE trượt 7 ngày.
- Retrain: `POST /internal/mlops/retrain` + job APScheduler hằng ngày. Kích hoạt khi MAPE trượt vượt ngưỡng hoặc có drift. Model mới chỉ lên `champion` nếu thắng model cũ trên tập holdout.
- Endpoint `GET /internal/mlops/status`: model hiện hành, metric, trạng thái drift, lịch sử retrain.
- Đánh giá IsolationForest bằng nhãn `is_injected_anomaly` và hai kịch bản trong `ai-service/src/data_pipeline/demo_scenarios.py`: precision, recall, F1.

**Mở rộng**: báo cáo HTML Evidently; nạp lại model nóng không cần restart.

**Sản phẩm bảo vệ**: demo bơm kịch bản `scenario_hvac_overrun.csv` → drift bật đỏ → retrain → model mới được promote.

---

## 4. TV3 — RAG & đánh giá (GenAI Specialist)

**Bắt buộc**
- Kho tri thức `ai-service/knowledge_base/*.md` (10–20 tài liệu ngắn): trích QCVN 09:2017/BXD, biểu giá điện EVN theo khung giờ, hướng dẫn vận hành Chiller/HVAC, mẹo tiết kiệm điện.
- Script ingest: cắt đoạn ~500 token, nhúng bằng model đa ngữ (`intfloat/multilingual-e5-small`), lưu ChromaDB nhúng.
- Tool mới `search_knowledge` trong `ai-service/src/agent/tools/`, nối vào `orchestrator.py`. Câu trả lời kèm danh sách nguồn (frontend đã có sẵn badge `domain_knowledge` ở `ChatMessage.jsx:3-17`).
- Dùng `history` mà endpoint đã nhận nhưng đang bỏ qua.
- Bộ 30 câu hỏi vàng + script đánh giá:
  - Truy xuất: hit-rate@3, MRR.
  - Câu trả lời: Ragas faithfulness và answer relevancy.
  - So sánh có RAG và không RAG.

**Mở rộng**: thay router từ khóa bằng function calling của Gemini; Ollama làm fallback offline; rerank.

**Sản phẩm bảo vệ**: bảng so sánh có/không RAG + demo câu hỏi về giá điện giờ cao điểm có trích nguồn.

---

## 5. TV4 — Backend: auth, ingest, SSE (Backend Lead)

**Bắt buộc**
- Prisma: thêm `User` (role `ADMIN` / `MANAGER` / `TECHNICIAN`), `RefreshToken`, `Zone` (thuộc `Building`, có `floor`, `name`), và `zone_id` tùy chọn trên `MeterReading`.
- Auth: `POST /api/v1/auth/{login,refresh,logout}`, bcrypt, access token ngắn hạn + refresh token xoay vòng (lưu hash trong DB); middleware `requireAuth`, `requireRole`.
- Khóa các endpoint đang mở: `POST /buildings`, `PATCH /anomalies/:id/status`, `POST /energy/cache/clear`.
- Ingest: `POST /api/v1/ingest/readings` (Zod) ghi `MeterReading`. Simulator ~10 zone gửi mỗi 2–5 giây, dùng lại `ai-service/src/data_pipeline/stream_worker.py`.
- SSE: `GET /api/v1/stream/readings` đẩy reading mới; `POST /api/v1/copilot/chat/stream` chuyển tiếp `StreamingResponse` từ FastAPI.
- Bảo mật cơ bản: `helmet`, `express-rate-limit`, CORS theo danh sách origin.

**Mở rộng**: Mosquitto MQTT thay HTTP ingest; `docker-compose.prod.yml` với Dockerfile multi-stage và `prisma migrate deploy`; Redis thay cache trong bộ nhớ.

**Sản phẩm bảo vệ**: sơ đồ luồng dữ liệu realtime + ma trận phân quyền theo vai trò + demo token hết hạn tự làm mới.

---

## 6. TV5 — Frontend: sơ đồ tầng, Copilot streaming, màn MLOps (Frontend Lead)

**Bắt buộc**
- `react-router` với các trang: Đăng nhập, Dashboard, Sơ đồ tầng, MLOps (chỉ Admin). Axios interceptor gắn token và tự refresh.
- Sơ đồ tầng 2D bằng SVG (1 tầng, 8–12 phòng): tô màu theo nhiệt độ / mức lãng phí, cập nhật qua SSE, bấm phòng xem chi tiết.
- Copilot: `react-markdown` + `remark-gfm` thay `MarkdownText` tự viết, hiển thị từng chữ khi streaming, nút dừng, hiển thị nguồn trích dẫn.
- Trang MLOps: model hiện hành và metric, trạng thái drift, lịch sử retrain, nút "Retrain" cho Admin, bảng benchmark của TV1.
- Thay bảng "Trạng thái hệ thống" đang hardcode (`frontend/src/App.jsx:59-64`) bằng dữ liệu `/health` thật.

**Mở rộng**: biểu đồ Recharts mini trong tin nhắn; KaTeX; khối 3D bằng Three.js.

**Sản phẩm bảo vệ**: demo trực tiếp một phòng chuyển đỏ khi có bất thường, bấm hỏi Copilot, câu trả lời chạy chữ kèm nguồn.

---

## 7. Hợp đồng API cần chốt ở tuần 1

| Endpoint | Bên cung cấp | Bên dùng |
|---|---|---|
| `GET /internal/forecast/predict` (24h tương lai) | TV1 | TV5 |
| `GET /internal/mlops/status`, `POST /internal/mlops/retrain` | TV2 | TV4 (proxy), TV5 |
| `POST /internal/copilot/chat/stream` (SSE: `token`, `sources`, `done`) | TV3 | TV4 (proxy), TV5 |
| `POST /api/v1/auth/*`, `GET /api/v1/stream/readings`, `GET /api/v1/buildings/:id/zones` | TV4 | TV5 |

Mỗi endpoint cần ghi rõ request/response mẫu (JSON) ngay trong tuần 1 để TV5 làm trước với dữ liệu mock.

---

## 8. Chất lượng và rủi ro

- Mỗi nhánh tự viết test cho phần mình (pytest cho `ai-service`, Vitest + Supertest cho `backend`). CI hiện tại phải xanh trước khi merge vào `develop`.

| Rủi ro | Cách giảm |
|---|---|
| Giai đoạn 0 trễ, các nhánh đo trên dữ liệu giả | Cả nhóm dồn sức tuần 1, chưa tách nhánh khi chưa xong |
| `torch` + `sentence-transformers` làm image Docker nặng | Dùng bản CPU, tách `requirements-ml.txt` |
| `EventSource` không gửi được header `Authorization` | Dùng `fetch` đọc stream thay `EventSource` |
| TV5 phụ thuộc mọi nhánh khác | Làm trước với mock theo hợp đồng mục 7 |
| Phần Mở rộng lấn thời gian phần Bắt buộc | Chỉ bắt đầu Mở rộng từ tuần 5 |

# 📘 Hướng Dẫn Cài Đặt & Vận Hành Hệ Thống EcoTrack
## (EcoTrack Setup, Deployment & Scientific Benchmark User Guide)

> **Mục tiêu Nghiên cứu Khoa học (NCKH):**  
> Xây dựng hệ thống giám sát và phát hiện bất thường năng lượng kết hợp giữa **Học máy không giám sát (Isolation Forest)** và **LLM Agent suy luận ngữ cảnh** (thời tiết, lịch trình vận hành tòa nhà, biểu giá điện EVN giờ cao điểm/thấp điểm) nhằm **giảm thiểu cảnh báo giả (False Positive Rate - FPR)** và **giải thích nguyên nhân gốc rễ bằng ngôn ngữ tự nhiên (Explainable AI - XAI với SHAP)**.

---

## 📑 Mục lục
1. [Yêu cầu Môi trường (Prerequisites)](#1-yêu-cầu-môi-trường-prerequisites)
2. [Hướng dẫn Cài đặt Từng Bước (Local Development)](#2-hướng-dẫn-cài-đặt-từng-bước-local-development)
3. [Hướng dẫn Chạy Thử nghiệm & Vận hành Hệ thống](#3-hướng-dẫn-chạy-thử-nghiệm--vận-hành-hệ-thống)
4. [Nghiên cứu Thực nghiệm: SHAP XAI & Đánh giá Chỉ số FPR](#4-nghiên-cứu-thực-nghiệm-shap-xai--đánh-giá-chỉ-số-fpr)
5. [Triển khai Nhanh bằng Docker Container](#5-triển-khai-nhanh-bằng-docker-container)
6. [Cấu trúc Thư mục Dự án](#6-cấu-trúc-thư-mục-dự-án)
7. [Xử lý Sự cố Thường gặp (Troubleshooting)](#7-xử-lý-sự-cố-thường-gặp-troubleshooting)

---

## 1. Yêu cầu Môi trường (Prerequisites)

Trước khi cài đặt, đảm bảo máy tính đã cài đặt các công cụ sau:

| Thành phần | Phiên bản khuyến nghị | Mục đích sử dụng |
| :--- | :--- | :--- |
| **Python** | `≥ 3.11.x` (hỗ trợ tốt 3.11 - 3.13) | Chạy FastAPI backend, ML models (XGBoost, Isolation Forest), SHAP, DeepEval |
| **Node.js & npm** | `Node ≥ 18.x` / `20.x` LTS, `npm ≥ 9.x` | Chạy Dashboard Frontend (React 18 + Vite + TailwindCSS + Lucide Icons) |
| **Docker & Docker Compose** | Docker Desktop `≥ 24.x`, Compose `≥ 2.24` | Chạy CSDL PostgreSQL 15 và đóng gói toàn bộ hệ thống |
| **Git** | `≥ 2.40` | Quản lý mã nguồn dự án |

*(Tùy chọn)* **API Keys LLM:**
- `GEMINI_API_KEY`: Kích hoạt Google Gemini 2.5 Flash làm LLM Copilot Agent.
- `OPENAI_API_KEY`: Hoặc sử dụng GPT-4o-mini làm mô hình suy luận ngữ cảnh.

---

## 2. Hướng dẫn Cài đặt Từng Bước (Local Development)

### Bước 2.1: Clone repository và tạo môi trường ảo Python
Mở Terminal / PowerShell tại thư mục làm việc:

```bash
# 1. Clone repository
git clone https://github.com/nhaphuong22/EcoTrack.git
cd EcoTrack

# 2. Khởi tạo môi trường ảo Python trong thư mục backend
cd backend
python -m venv venv

# 3. Kích hoạt môi trường ảo:
# Trên Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# Trên Windows (CMD):
venv\Scripts\activate.bat
# Trên Linux / macOS:
source venv/bin/activate
```

### Bước 2.2: Cài đặt các thư viện phụ thuộc (Dependencies)
Cài đặt toàn bộ backend stack bao gồm FastAPI, Machine Learning, XAI (SHAP), DeepEval và công cụ trực quan:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Bước 2.3: Thiết lập biến môi trường (`.env`)
Sao chép file mẫu cấu hình sang `.env`:

```bash
# Đang đứng tại thư mục backend/
cp .env.example .env
```

Nội dung file `backend/.env` cơ bản:
```ini
APP_ENV=development
PORT=8000
DATABASE_URL=postgresql://ecotrack:ecotrack_secret@localhost:5432/ecotrack
# Nếu không bật PostgreSQL, hệ thống tự động fallback sang SQLite local: ecotrack_local.db

# API Key cho LLM Copilot Agent (điền nếu có):
GEMINI_API_KEY=your-gemini-api-key
OPENAI_API_KEY=your-openai-api-key

TARIFF_RATE_VND=3100
```

### Bước 2.4: Chạy Migration CSDL qua Alembic
Áp dụng lược đồ CSDL và các chỉ mục hiệu năng (Composite Indexes cho chuỗi thời gian) lên Database:

```bash
# Đang đứng tại thư mục backend/
alembic upgrade head
```

### Bước 2.5: Nạp dữ liệu mẫu sạch (`seed_data.py`)
Khởi tạo danh sách các tòa nhà tiêu chuẩn (Văn phòng, Trung tâm thương mại, Giảng đường) và 168 giờ đo baseline từ tập dữ liệu ASHRAE / BDG2:

```bash
# Đang đứng tại thư mục backend/
python seed_data.py
```
*Kết quả:* Hệ thống sẽ tự động khởi tạo các bảng và nạp đầy đủ dữ liệu đo lường sạch sẵn sàng cho suy luận.

### Bước 2.6: Cài đặt Frontend React (Tùy chọn cho giao diện người dùng)
Mở cửa sổ terminal thứ 2 tại thư mục gốc `EcoTrack`:

```bash
cd frontend
npm install
```

---

## 3. Hướng dẫn Chạy Thử nghiệm & Vận hành Hệ thống

### 3.1. Khởi động Backend API Server (FastAPI)
Chạy server API FastAPI với chế độ Hot-Reload:

```bash
# Tại thư mục backend/:
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Truy cập các địa chỉ tương tác:
* 🔌 **API Health Check:** [http://localhost:8000/health](http://localhost:8000/health)
* 📚 **Interactive Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs)
* 📖 **ReDoc Documentation:** [http://localhost:8000/redoc](http://localhost:8000/redoc)

### 3.2. Khởi động Stream Data Worker (Mô phỏng IoT Telemetry thời gian thực)
Stream Data Worker giả lập tín hiệu gửi về từ các đồng hồ thông minh (smart meter) từng giây:

```bash
# Tại thư mục backend/:
python src/data_pipeline/stream_worker.py
```
Console sẽ hiển thị dòng telemetry liên tục theo định dạng:
```text
⚡ [2026-10-07 14:00:00] Building: B-OFFICE-01 | Meter: 284.50 kWh | Temp: 34.2°C
```

### 3.3. Khởi động Giao diện Frontend (React + Vite)
```bash
# Tại thư mục frontend/:
npm run dev
# Truy cập giao diện: http://localhost:3000
```

### 3.4. Chạy Toàn Bộ Kiểm Thử Tự Động (Full Automated Test Suite)
Chạy 46 test cases kiểm chứng trọn vẹn toàn bộ pipeline:

```bash
# Tại thư mục backend/:
pytest tests/ -v
```
*(Kết quả yêu cầu: **46/46 PASSED**)*

---

## 4. Nghiên cứu Thực nghiệm: SHAP XAI & Đánh giá Chỉ số FPR

Hệ thống cung cấp sẵn script chuyên biệt phục vụ trích xuất kết quả thực nghiệm đưa vào bài báo khoa học.

### 4.1. Lệnh chạy thực nghiệm
```bash
# Tại thư mục backend/:
python experiments/run_xai_and_evaluation.py
```

### 4.2. Giải thích 2 giai đoạn thực nghiệm:

#### 🔹 Giai đoạn 1: Trích xuất giải thích dị thường (XAI) qua SHAP TreeExplainer
Module `src/models/explainability.py` tính toán giá trị SHAP cục bộ cho từng mẫu đo:
* Đánh giá mức độ ảnh hưởng của từng đặc trưng: Độ lệch dự báo (`residual`), Điện năng thực tế (`meter_reading_kwh`), Nhiệt độ môi trường (`outdoor_temperature_c`), Giờ trong ngày (`hour`).
* Tự động sinh câu tóm tắt bằng ngôn ngữ tự nhiên:
  > *"Điểm đo có sự đóng góp lớn nhất từ 3 đặc trưng: Độ lệch so với dự báo baseline = 84.2 kWh (SHAP: -2.5824); Điện năng tiêu thụ thực tế = 312.5 kWh (SHAP: -1.7948); Nhiệt độ môi trường = 35.8°C (SHAP: -0.9239)."*

#### 🔹 Giai đoạn 2: Đo lường mức độ giảm Cảnh báo giả (False Positive Rate - FPR)
Module `src/models/evaluation_metrics.py` so sánh:
* **Mô hình Baseline (Chỉ dùng Isolation Forest không giám sát):** Thường nhạy quá mức và phát còi báo động sai khi trời nắng nóng đột ngột hoặc tòa nhà tăng ca ngoài giờ.
* **Mô hình Đề xuất (Kết hợp Isolation Forest + LLM Context Agent):** Agent truy vấn dữ liệu thời tiết thực và lịch đặt phòng để xác nhận nguyên nhân hợp lệ, triệt tiêu cảnh báo giả.

**Bảng Chỉ Số Đưa Vào Bài Báo Khoa Học (Benchmark Results):**
| Chỉ số Đánh Giá | Baseline (Isolation Forest) | Proposed (IF + LLM Agent) | Cải Thiện (Delta) |
| :--- | :--- | :--- | :--- |
| **False Positive Rate (FPR)** | 27.50% | 5.00% | **-81.8% (Triệt tiêu báo giả)** |
| **Số cảnh báo giả (FP count)** | 22 cảnh báo | 4 cảnh báo | **-18 cảnh báo giả** |
| **Precision (Độ chuẩn xác)** | 46.34% | 82.61% | **+36.27%** |
| **Recall (Độ nhạy bắt lỗi thật)** | 95.00% | 95.00% | **100% bảo toàn lỗi thật** |
| **F1-Score** | 0.6230 | 0.8837 | **+0.2607** |

---

## 5. Triển khai Nhanh bằng Docker Container

Nếu muốn khởi chạy toàn bộ hệ thống (**PostgreSQL**, **FastAPI Backend**, **React Frontend**) trong môi trường cô lập chỉ với **1 lệnh duy nhất**:

```bash
# Tại thư mục gốc EcoTrack:
docker compose up --build
```

Để chạy ngầm dưới dạng background daemon:
```bash
docker compose up -d
```

Để kiểm tra trạng thái các container:
```bash
docker compose ps
```

Để tắt toàn bộ hệ thống:
```bash
docker compose down
```

| Service | Container Name | Cổng ngoài (Host) | Chức năng |
| :--- | :--- | :--- | :--- |
| **Database** | `ecotrack_postgres` | `5432` | CSDL quan hệ lưu trữ dữ liệu đo và sự cố |
| **Backend** | `ecotrack_backend` | `8000` | FastAPI server + ML Inference + XAI |
| **Frontend** | `ecotrack_frontend` | `3000` | Web UI Dashboard giám sát năng lượng |

---

## 6. Cấu trúc Thư mục Dự án

```text
EcoTrack/
├── backend/
│   ├── alembic/                      # Alembic schema migrations
│   │   └── versions/                 # Các phiên bản migration
│   ├── alembic.ini                   # Cấu hình kết nối Alembic
│   ├── experiments/                  # Scripts thực nghiệm NCKH & Benchmarks
│   │   ├── benchmark/                # Dữ liệu 4 Case Studies thực tế
│   │   ├── run_benchmark.py          # Benchmark độ chính xác của Agent & Tool Calling
│   │   └── run_xai_and_evaluation.py # Thực nghiệm SHAP TreeExplainer & FPR metrics
│   ├── seed_data.py                  # Script nạp dữ liệu mẫu sạch
│   ├── requirements.txt              # Danh sách thư viện Python
│   ├── src/
│   │   ├── agent/                    # LLM Copilot Orchestrator & Tool Registry
│   │   ├── api/                      # REST API Endpoints (FastAPI)
│   │   ├── data_pipeline/            # Ingestion, Feature Engineering & Stream Worker
│   │   ├── database.py               # Engine SQLAlchemy, Connection Pool & Alembic runner
│   │   └── models/
│   │       ├── anomaly_isolation_forest/ # Mô hình Isolation Forest
│   │       ├── forecaster_xgboost/       # Mô hình dự báo phụ tải XGBoost
│   │       ├── explainability.py         # Module XAI SHAP TreeExplainer
│   │       ├── evaluation_metrics.py     # Module đo lường FPR, Precision, Recall, F1
│   │       └── db_models.py              # Lược đồ ORM SQLAlchemy
│   └── tests/                        # 46 Unit & Integration Tests (100% passed)
├── frontend/                         # Dashboard React 18 + Vite + TailwindCSS
├── docs/                             # Tài liệu kỹ thuật, báo cáo NCKH & User Guide
│   ├── SETUP_AND_USAGE_GUIDE.md      # Tài liệu này
│   └── ECOTRACK_SCIENTIFIC_REPORT_DRAFT.md
├── docker-compose.yml                # Docker orchestrator 3 tầng
└── README.md                         # Giới thiệu tổng quan dự án
```

---

## 7. Xử lý Sự cố Thường gặp (Troubleshooting)

### Q1: Bị lỗi `Connection refused` tới PostgreSQL cổng 5432?
* **Giải pháp:** Hệ thống đã tích hợp sẵn cơ chế **tự động fallback sang SQLite local** (`backend/ecotrack_local.db`). Bạn vẫn có thể chạy và kiểm thử bình thường mà không bắt buộc phải bật PostgreSQL. Nếu muốn dùng PostgreSQL, hãy chạy:
  ```bash
  docker compose up -d db
  ```

### Q2: Chạy `pytest` báo lỗi thiếu package?
* **Giải pháp:** Đảm bảo bạn đã kích hoạt virtual environment và cài đặt đúng requirements:
  ```bash
  pip install -r backend/requirements.txt
  ```

### Q3: Lỗi font chữ tiếng Việt trên Windows CMD khi in SHAP summary?
* **Giải pháp:** Trong các script đã tích hợp `sys.stdout.reconfigure(encoding='utf-8')`. Khi chạy trên CMD, bạn có thể gõ lệnh `chcp 65001` trước khi chạy script.

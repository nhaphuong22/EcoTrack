# EcoTrack — AI-Powered Building Energy Management Platform

> Phân tích và tối ưu năng lượng tòa nhà thông minh với **XGBoost**, **Isolation Forest**, và **LLM Agent (Gemini / OpenAI)**.

---

## 🚀 Hướng Dẫn Cài Đặt & Khởi Chạy (Từ A - Z)

Dự án được tối ưu để thiết lập môi trường, chạy migration và khởi chạy đồng thời toàn bộ hệ thống (**AI Service FastAPI**, **Backend Express Gateway**, và **Frontend React Vite**) với các lệnh đơn giản ngay từ thư mục gốc.

### 📋 Yêu cầu môi trường
- **Docker Desktop** (đang bật để chạy CSDL PostgreSQL)
- **Node.js** (≥ 18.x) & **Python** (≥ 3.10)

---

### Bước 1: Cài đặt thư viện (Chỉ thực hiện lần đầu)

Mở terminal tại thư mục gốc `EcoTrack` và chạy 1 lệnh duy nhất:

```bash
npm run install:all
```

*(Lệnh này tự động cài đặt tuần tự: thư viện Express/Prisma cho `backend/`, thư viện React/Tailwind cho `frontend/`, và gói Python Machine Learning từ `ai-service/requirements.txt`)*.

---

### Bước 2: Khởi động CSDL & Chạy Migrations

1. **Khởi động PostgreSQL trong Docker**:
   ```bash
   npm run db:up
   ```
   *(Container `ecotrack_postgres` sẽ khởi chạy ngầm tại cổng `5432`)*.

2. **Chạy Prisma Migration**:
   ```bash
   npm run db:migrate
   ```
   *(Áp dụng các file SQL migration chính thức vào PostgreSQL. Bạn cũng có thể dùng `npm run db:push` để đồng bộ nhanh schema)*.

3. *(Tùy chọn)* **Mở giao diện Web xem dữ liệu (Prisma Studio)**:
   ```bash
   npm run db:studio
   ```
   👉 Truy cập **`http://localhost:5555`** để xem và chỉnh sửa dữ liệu dạng bảng trực quan.

---

### Bước 3: Khởi chạy dự án (Run Dev)

Tại thư mục gốc `EcoTrack`, chạy:

```bash
npm run dev
```

#### ⚡ Lệnh này sẽ chạy trực tiếp 3 dịch vụ bằng dòng lệnh (không dùng docker):
- 🟣 **`[AI]`**: Pure Python FastAPI tại `http://localhost:8000` (XGBoost, Isolation Forest & Copilot).
- 🟢 **`[BACKEND]`**: Express.js Gateway tại `http://localhost:5000` (Prisma ORM, CRUD, In-memory cache).
- 🔵 **`[FRONTEND]`**: React Vite tại `http://localhost:3000` (Hot-Reload tức thì khi sửa code).

| Dịch vụ | URL / Địa chỉ | Chức năng |
| :--- | :--- | :--- |
| 💻 **Dashboard UI** | **http://localhost:3000** | Giao diện giám sát năng lượng, biểu đồ & AI Copilot |
| 🔌 **Backend API** | **http://localhost:5000** | Express.js API Gateway, CRUD, Cache TTL & Proxy |
| 🧠 **AI Service** | **http://localhost:8000** | Pure Python FastAPI — ML Inference & ReAct Copilot |
| 📚 **AI Swagger Docs** | **http://localhost:8000/docs** | Swagger Docs tài liệu kiểm thử AI Engine |
| 🗄️ **PostgreSQL DB** | `localhost:5432` | DB: `ecotrack` \| User: `ecotrack` \| Pass: `ecotrack_secret` |
| 🖥️ **Prisma Studio** | `http://localhost:5555` | Giao diện quản lý CSDL |

> 💡 **Cách dừng hệ thống:** Nhấn **`Ctrl + C`** tại cửa sổ Terminal đang chạy.
> 
> 🐳 **Muốn chạy kèm tự động bật Docker DB:** Dùng lệnh `npm run dev:docker`.  
> 🐳 **Muốn chạy Full 4 Containers qua Docker Compose:** Dùng lệnh `docker compose up`.

---

### Bước 4: Chạy kiểm thử tự động (Automated Testing)

```bash
# Chạy toàn bộ 51 tests (Pytest + Vitest)
npm test

# Hoặc kiểm thử riêng từng phần:
npm run test:backend   # 20 tests Vitest (Express Gateway)
npm run test:ai        # 31 tests Pytest (AI ML Engine)
```

---

## 📐 Kiến trúc hệ thống

```
EcoTrack Monorepo
├── backend/                    # [MỚI] Node.js · Express · Prisma · API Gateway (Port 5000)
│   ├── prisma/schema.prisma    # PostgreSQL Schema & Indexes
│   ├── src/
│   │   ├── routes/             # buildings, energy, forecast, anomalies, copilot
│   │   ├── services/           # buildingService, anomalyService
│   │   ├── utils/              # aiClient (Proxy to FastAPI), InMemoryTTLCache
│   │   └── server.js           # Express App Entrypoint
│   └── tests/                  # Vitest + Supertest Gateway Tests
│
├── ai-service/                 # [CHUYỂN ĐỔI] Pure Python · FastAPI (Port 8000)
│   ├── src/
│   │   ├── data_pipeline/      # BDG2 data loader, Feature Engineering, Streaming worker
│   │   ├── models/             # XGBoost Forecaster (24h) & Isolation Forest Anomaly
│   │   ├── agent/              # ReAct Copilot (Gemini / OpenAI Tools)
│   │   └── api/routers/        # /internal endpoints + /api/v1 compatible routes
│   └── tests/                  # Pytest Unit & Integration Tests (42 tests)
│
└── frontend/                   # React 18 · Vite · TailwindCSS · Recharts (Port 3000)
    └── src/
        ├── components/         # MetricCards · ForecastChart · AnomalyTable · CopilotDrawer
        └── services/api.js     # Axios client kết nối Express Backend (:5000)
```

---

## 🧠 Công nghệ AI/ML

| Module | Thuật toán | Mục tiêu chất lượng |
| :--- | :--- | :--- |
| **Forecasting** | XGBoost (n_est=120, lr=0.06) | MAPE ≤ 10% |
| **Anomaly Detection** | Isolation Forest (contamination=4%) | Precision ≥ 85%, FPR ≤ 12% |
| **Copilot Agent** | Google Gemini 1.5 Flash / GPT-4o-mini | 1st token < 2.5s |

---

## 👥 Phân chia team (5 thành viên)

| Thành viên | Phụ trách |
| :--- | :--- |
| **Thành viên 1** | `backend/src/data_pipeline/` — ETL, Feature Engineering BDG2 |
| **Thành viên 2** | `backend/src/models/forecaster_xgboost/` — XGBoost Training & Inference |
| **Thành viên 3** | `backend/src/models/anomaly_isolation_forest/` — Isolation Forest & Thresholding |
| **Thành viên 4** | `backend/src/agent/` + `backend/src/api/` — LLM Agent & FastAPI Backend |
| **Thành viên 5** | `frontend/src/` — React Dashboard & Copilot UI |

---

## 🌿 Quy trình làm việc nhóm với Git (Git Workflow)

- **Nhánh `main`**: Chỉ lưu code ổn định nhất để demo / nộp bài.
- **Nhánh `develop`**: Nhánh tích hợp chính của cả nhóm trong suốt quá trình phát triển.
- **Quy tắc tạo branch**: Nhánh tính năng luôn tạo từ `develop` theo định dạng:
  ```bash
  git checkout develop
  git pull origin develop
  git checkout -b feature/<tên-thành-viên>-<tính-năng>
  ```
- **Quy trình Pull Request (PR)**:
  - Tuyệt đối **không** push trực tiếp lên `main` hoặc `develop`.
  - Luôn mở **Pull Request (PR)** vào nhánh `develop`.
  - Cần ít nhất **1 thành viên trong nhóm review** và chấp thuận trước khi merge.

---

## 🛠️ Công cụ hỗ trợ phát triển (Developer Tools)

- **Quản lý CSDL trực quan trên Web (Prisma Studio):**
  ```bash
  npm run db:studio
  ```
- **Chạy Stream Telemetry Worker (Mô phỏng IoT telemetry):**
  ```bash
  python ai-service/src/data_pipeline/stream_worker.py
  ```
- **Chạy kiểm thử toàn diện:**
  ```bash
  npm test
  ```

---

## 📄 Tài liệu thiết kế dự án

| Tài liệu | Đường dẫn | Mô tả |
| :--- | :--- | :--- |
| 📋 **PRD** | `_bmad-output/planning-artifacts/prds/prd-EcoTrack-2026-09-23/prd.md` | Tài liệu đặc tả yêu cầu sản phẩm |
| 🏛️ **Architecture Spine** | `_bmad-output/planning-artifacts/architecture/architecture-EcoTrack-2026-09-23/ARCHITECTURE-SPINE.md` | Thiết kế kiến trúc kỹ thuật hệ thống |
| 🔧 **Technical Addendum** | `_bmad-output/planning-artifacts/prds/prd-EcoTrack-2026-09-23/addendum.md` | Phụ lục kỹ thuật và chuẩn tích hợp |

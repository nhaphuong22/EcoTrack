# EcoTrack — AI-Powered Building Energy Management Platform

> Phân tích và tối ưu năng lượng tòa nhà thông minh với **XGBoost**, **Isolation Forest**, và **LLM Agent (Gemini / OpenAI)**.

---

## 🚀 Khởi chạy dự án (Chỉ 1 lệnh duy nhất)

Dự án được tối ưu để khởi chạy đồng thời toàn bộ hệ thống (**Database PostgreSQL**, **Backend FastAPI**, và **Frontend React Vite**) chỉ bằng **1 lệnh duy nhất** trong cùng một cửa sổ Terminal, hỗ trợ **Hot-Reload / Auto-Reload** tự động khi sửa code.

### 📋 Yêu cầu môi trường
- **Docker Desktop** (đang bật để chạy CSDL PostgreSQL)
- **Python** (≥ 3.10) & **Node.js** (≥ 18.x)
- *(Tuỳ chọn)* Điền `GEMINI_API_KEY` hoặc `OPENAI_API_KEY` vào file `backend/.env` để kích hoạt trợ lý AI Copilot.

---

### Bước 1: Cài đặt thư viện (Chỉ thực hiện lần đầu tiên)

Mở terminal tại thư mục gốc `EcoTrack`:

```bash
# Tạo file cấu hình môi trường cho backend từ mẫu
cp backend/.env.example backend/.env

# Cài đặt thư viện Backend Python
pip install -r backend/requirements.txt

# Cài đặt thư viện Frontend React
npm install --prefix frontend
```

---

### Bước 2: Khởi chạy dự án

Tại thư mục gốc `EcoTrack`, chỉ cần chạy:

```bash
npm run dev
```

*(Trên Windows, bạn cũng có thể gõ `.\dev.bat` hoặc **nhấp đúp chuột vào file `dev.bat`** để chạy ngay).*

#### ⚡ Lệnh này sẽ tự động:
1. 🐘 **Khởi động CSDL PostgreSQL** ngầm trong Docker (`ecotrack_postgres` - cổng 5432).
2. 🔌 **Khởi động Backend FastAPI** tại `http://localhost:8000` (tự động reload khi sửa code Python).
3. 💻 **Khởi động Frontend React Vite** tại `http://localhost:3000` (tự động cập nhật giao diện tức thì khi sửa UI).

| Dịch vụ | URL / Địa chỉ | Chức năng |
| :--- | :--- | :--- |
| 💻 **Dashboard UI** | **http://localhost:3000** | Giao diện giám sát năng lượng, biểu đồ & AI Copilot |
| 🔌 **Backend API** | **http://localhost:8000** | REST API tính toán năng lượng & suy luận ML |
| 📚 **Swagger Docs** | **http://localhost:8000/docs** | Tài liệu kiểm thử API tương tác trực quan |
| 🗄️ **PostgreSQL DB** | `localhost:5432` | DB: `ecotrack` \| User: `ecotrack` \| Pass: `ecotrack_secret` |

> 💡 **Cách dừng hệ thống:** Nhấn **`Ctrl + C`** tại cửa sổ Terminal đang chạy.

---

## 📐 Kiến trúc hệ thống

```
EcoTrack Monorepo
├── backend/                    # FastAPI · XGBoost · Isolation Forest · LLM Agent
│   ├── src/
│   │   ├── data_pipeline/      # Building Data Genome 2 loader + Feature Engineering
│   │   ├── models/
│   │   │   ├── forecaster_xgboost/        # Dự báo phụ tải 24h
│   │   │   └── anomaly_isolation_forest/  # Phát hiện bất thường
│   │   ├── agent/              # LLM Copilot (ReAct · Tool Calling)
│   │   └── api/                # FastAPI routers + Pydantic schemas
│   └── configs/                # model_config.yaml · agent_config.yaml
│
└── frontend/                   # React 18 · Vite · TailwindCSS · Recharts
    └── src/
        ├── components/dashboard/  # MetricCards · ForecastChart · AnomalyTable
        ├── components/copilot/    # CopilotDrawer · ChatMessage · QuickPrompts
        ├── hooks/                 # useEnergyData · useCopilot
        └── services/api.js        # Axios client
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

## 📄 Tài liệu dự án

| Tài liệu | Đường dẫn |
| :--- | :--- |
| 📋 PRD | `_bmad-output/planning-artifacts/prds/prd-EcoTrack-2026-09-23/prd.md` |
| 🏛️ Architecture Spine | `_bmad-output/planning-artifacts/architecture/architecture-EcoTrack-2026-09-23/ARCHITECTURE-SPINE.md` |
| 🔧 Technical Addendum | `_bmad-output/planning-artifacts/prds/prd-EcoTrack-2026-09-23/addendum.md` |

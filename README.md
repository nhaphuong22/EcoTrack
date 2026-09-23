# EcoTrack — AI-Powered Building Energy Management Platform

> Phân tích và tối ưu năng lượng tòa nhà thông minh với **XGBoost**, **Isolation Forest**, và **LLM Agent (Gemini / OpenAI)**.

---

## 🚀 Khởi chạy nhanh (5 phút)

### Yêu cầu hệ thống
- Docker Desktop ≥ 24.x + Docker Compose ≥ 2.24
- (Tuỳ chọn) Google Gemini API Key hoặc OpenAI API Key để kích hoạt Copilot Agent

### Bước 1: Clone và cấu hình môi trường
```bash
git clone <repo-url>
cd EcoTrack

# Tạo file .env cho backend từ mẫu
cp backend/.env.example backend/.env

# (Tuỳ chọn) Điền API Key vào backend/.env
# GEMINI_API_KEY=your-gemini-api-key
# OPENAI_API_KEY=your-openai-api-key
```

### Bước 2: Khởi chạy toàn bộ hệ thống
```bash
docker-compose up --build
```

| Service          | URL                           |
| :--------------- | :---------------------------- |
| 🔌 Backend API   | http://localhost:8000          |
| 📚 Swagger Docs  | http://localhost:8000/docs     |
| 💻 Dashboard UI  | http://localhost:3000          |

---

## 🛠️ Phát triển local (không Docker)

### Backend (Python FastAPI)
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env          # Điền API key nếu có
uvicorn src.main:app --reload --port 8000
```

### Frontend (React + Vite)
```bash
cd frontend
npm install
npm run dev
# → http://localhost:3000
```

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

## 📄 Tài liệu dự án

| Tài liệu | Đường dẫn |
| :--- | :--- |
| 📋 PRD | `_bmad-output/planning-artifacts/prds/prd-EcoTrack-2026-09-23/prd.md` |
| 🏛️ Architecture Spine | `_bmad-output/planning-artifacts/architecture/architecture-EcoTrack-2026-09-23/ARCHITECTURE-SPINE.md` |
| 🔧 Technical Addendum | `_bmad-output/planning-artifacts/prds/prd-EcoTrack-2026-09-23/addendum.md` |

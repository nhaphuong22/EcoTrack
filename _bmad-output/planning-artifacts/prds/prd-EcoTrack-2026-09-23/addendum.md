# EcoTrack Technical Addendum: Decoupled Architecture & System Specifications

This document defines the technical architecture, mathematical formulations, and API specifications for **EcoTrack**, operating with a **FastAPI backend** and a **React frontend**.

---

## 1. System Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                 React Frontend (Vite SPA)                   │
│  - Time-series Forecast Chart (Recharts)                    │
│  - Anomaly Triage Kanban & Metric Cards                     │
│  - Copilot Chat Drawer (Streaming Markdown & Tool Badges)   │
└──────────────────────────────▲──────────────────────────────┘
                               │ HTTP / SSE / WebSocket
┌──────────────────────────────▼──────────────────────────────┐
│                    FastAPI Backend                          │
│                                                             │
│  ├── /api/v1/energy       ──► Ingestion & Telemetry Query   │
│  ├── /api/v1/forecast     ──► XGBoost Predictive Engine     │
│  ├── /api/v1/anomalies    ──► Isolation Forest Detector     │
│  └── /api/v1/copilot      ──► Cloud LLM Agent (ReAct Loop)  │
└───────▲──────────────────────▲──────────────────────▲───────┘
        │                      │                      │
┌───────┴────────┐     ┌───────┴────────┐     ┌───────┴────────┐
│ XGBoost Model  │     │ Isolation      │     │ Cloud LLM API  │
│ - Lag features │     │ Forest         │     │ - Gemini /     │
│ - Weather join │     │ - Residuals    │     │   OpenAI       │
│ - 95% Conf Int │     │ - Severity map │     │ - Tool Calling │
└────────────────┘     └────────────────┘     └────────────────┘
        ▲                      ▲
        └──────────────┬───────┘
                       │
         ┌─────────────┴─────────────┐
         │ Building Data Genome 2 /  │
         │ ASHRAE Hourly Telemetry   │
         │ (SQLite / Parquet Cache)  │
         └───────────────────────────┘
```

---

## 2. Decoupled Directory Structure

```text
EcoTrack/
├── _bmad-output/
│   └── planning-artifacts/prds/prd-EcoTrack-2026-09-23/
│       ├── prd.md                      # PRD chính thức
│       ├── addendum.md                 # Phụ lục kỹ thuật & API specs
│       └── .memlog.md                  # Nhật ký quyết định của BMad
│
├── backend/                            # Toàn bộ mã nguồn Backend & AI/ML
│   ├── configs/
│   │   ├── base_config.yaml            # Cấu hình server, database, paths
│   │   ├── model_config.yaml           # Hyperparameters XGBoost & Isolation Forest
│   │   └── agent_config.yaml           # Provider (Gemini/OpenAI), prompts, tools
│   │
│   ├── data/
│   │   ├── raw/                        # Building Data Genome 2 CSV samples
│   │   └── processed/                  # Cached parquet/sqlite datasets
│   │
│   ├── src/
│   │   ├── api/                        # FastAPI Layer
│   │   │   ├── main.py                 # FastAPI Application & CORS configuration
│   │   │   ├── routers/
│   │   │   │   ├── energy.py           # Endpoints lấy dữ liệu đo thực tế
│   │   │   │   ├── forecast.py         # Endpoints gọi XGBoost dự báo
│   │   │   │   ├── anomalies.py        # Endpoints danh sách bất thường
│   │   │   │   └── copilot.py          # Endpoint streaming chat với LLM Agent
│   │   │   └── schemas/                # Pydantic v2 Models (DTOs)
│   │   │
│   │   ├── data_pipeline/              # ETL & Preprocessing
│   │   │   ├── bdg2_loader.py          # Loader dữ liệu Building Data Genome 2 / ASHRAE
│   │   │   ├── preprocessor.py         # Làm sạch, tính Lag 1h/24h/168h, rolling stats
│   │   │   └── weather_enricher.py     # Nối nhiệt độ/độ ẩm tương ứng theo timestamp
│   │   │
│   │   ├── models/                     # ML Core Models
│   │   │   ├── forecaster_xgboost/     # XGBoost Model trainer & inference
│   │   │   │   ├── trainer.py          # TimeSeriesSplit cross-validation
│   │   │   │   └── predictor.py        # 24-hour horizon predictor + 95% interval
│   │   │   │
│   │   │   ├── anomaly_isolation_forest/
│   │   │   │   ├── detector.py         # Isolation Forest model wrapper
│   │   │   │   └── thresholding.py     # Phân loại Low/Medium/Critical
│   │   │   │
│   │   │   └── artifacts/              # File checkpoint .joblib
│   │   │
│   │   └── agent/                      # LLM Copilot & Tools
│   │       ├── orchestrator.py         # Vòng lặp Agent gọi Gemini API / OpenAI
│   │       ├── prompts.py              # System prompt chuyên gia năng lượng tòa nhà
│   │       └── tools/
│   │           ├── telemetry_tool.py   # Tool đọc kWh lịch sử
│   │           ├── forecast_tool.py    # Tool đọc kết quả dự báo XGBoost
│   │           ├── anomaly_tool.py     # Tool đọc log lỗi Isolation Forest
│   │           └── tariff_tool.py      # Tool ước tính chi phí lãng phí
│   │
│   ├── tests/                          # Pytest unit tests
│   ├── requirements.txt                # Dependencies (fastapi, uvicorn, xgboost, scikit-learn, google-genai)
│   └── .env.example                    # GEMINI_API_KEY / OPENAI_API_KEY
│
├── frontend/                           # Single Page Application (React)
│   ├── public/
│   ├── src/
│   │   ├── assets/
│   │   ├── components/                 # React UI Components
│   │   │   ├── layout/
│   │   │   │   ├── Header.jsx          # Header với trạng thái tòa nhà & bộ lọc ngày
│   │   │   │   └── Sidebar.jsx
│   │   │   ├── dashboard/
│   │   │   │   ├── MetricCards.jsx     # Tổng kWh, Đỉnh phụ tải (Peak kW), EUI, Anomaly count
│   │   │   │   ├── ForecastChart.jsx   # Biểu đồ Recharts: Actual vs. Forecast + Bounds
│   │   │   │   └── AnomalyTable.jsx    # Danh sách cảnh báo kèm badge mức độ
│   │   │   └── copilot/
│   │   │       ├── CopilotDrawer.jsx   # Cửa sổ slide-over chat đàm thoại
│   │   │       ├── ChatMessage.jsx     # Render Markdown & Tool invocation badge
│   │   │       └── QuickPrompts.jsx    # Gợi ý câu hỏi nhanh (Chẩn đoán lỗi, báo cáo tuần)
│   │   │
│   │   ├── services/
│   │   │   └── api.js                  # Axios/Fetch client kết nối FastAPI
│   │   ├── hooks/                      # Custom hooks (useEnergyData, useCopilotChat)
│   │   ├── App.jsx                     # Layout chính
│   │   ├── main.jsx
│   │   └── index.css                   # TailwindCSS tokens & styles
│   ├── package.json
│   ├── vite.config.js
│   └── tailwind.config.js
│
├── README.md
└── docker-compose.yml                  # Khởi chạy đồng thời Backend & Frontend
```

---

## 3. API Contract (FastAPI & React)

### 3.1 Get Telemetry & Forecast
- **Endpoint**: `GET /api/v1/energy/timeseries`
- **Params**: `building_id=chiller_tower_1&start_date=2026-08-01&end_date=2026-08-07`
- **Response**:
```json
{
  "building_id": "chiller_tower_1",
  "data": [
    {
      "timestamp": "2026-08-01T00:00:00Z",
      "actual_kwh": 142.5,
      "predicted_kwh": 138.2,
      "lower_bound_95": 125.0,
      "upper_bound_95": 151.4,
      "outdoor_temp_c": 26.4,
      "is_anomaly": false,
      "anomaly_score": 0.32
    },
    {
      "timestamp": "2026-08-01T01:00:00Z",
      "actual_kwh": 195.0,
      "predicted_kwh": 135.0,
      "lower_bound_95": 122.0,
      "upper_bound_95": 148.0,
      "outdoor_temp_c": 25.8,
      "is_anomaly": true,
      "anomaly_score": 0.86,
      "severity": "Critical"
    }
  ]
}
```

### 3.2 List Anomalies
- **Endpoint**: `GET /api/v1/anomalies/events`
- **Params**: `building_id=chiller_tower_1&status=open`
- **Response**:
```json
[
  {
    "id": "ANOM-20260801-01",
    "timestamp": "2026-08-01T01:00:00Z",
    "subsystem": "Chiller Plant Loop 2",
    "severity": "Critical",
    "anomaly_score": 0.86,
    "delta_kwh": 60.0,
    "estimated_cost_waste_usd": 10.80,
    "status": "New"
  }
]
```

### 3.3 Copilot Streaming Conversation
- **Endpoint**: `POST /api/v1/copilot/chat`
- **Request Body**:
```json
{
  "message": "Phân tích giúp tôi sự cố ANOM-20260801-01 lúc 1h sáng ngày 1/8",
  "building_id": "chiller_tower_1",
  "history": []
}
```
- **Response (Server-Sent Events)**:
  - Stream chunks of Markdown text + Tool execution markers (`[TOOL_EXECUTION: get_anomaly_details(id="ANOM-20260801-01")]`).

---

## 4. Benchmark Dataset Specifications (Building Data Genome 2)
- **Source**: Miller et al., *The Building Data Genome 2 Project* (Nature Scientific Data).
- **Features Used**:
  - `timestamp`: Hourly resolution.
  - `meter_reading`: Electricity load (kWh).
  - `air_temperature`: Outdoor dry bulb (°C).
  - `dew_temperature`, `relative_humidity`: Air moisture.
  - `primary_use`: Commercial office / Education / Healthcare.
  - `square_feet`: Floor area for EUI normalization.

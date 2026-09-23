---
title: "EcoTrack: AI-Powered Building Energy Management & Optimization Platform"
status: draft
created: 2026-09-23
updated: 2026-09-23
---

# PRD: EcoTrack Building Energy Analytics & Copilot

## 0. Document Purpose
This Product Requirements Document (PRD) defines the scope, functional requirements, and system characteristics for **EcoTrack**—an intelligent Building Energy Management System (BEMS) leveraging **XGBoost** for load forecasting, **Isolation Forest** for multivariate anomaly detection, and an autonomous **LLM Agent** (Google Gemini API / OpenAI) for natural language root cause diagnostics and energy efficiency recommendations.

The architecture is decoupled into a high-performance **FastAPI backend** (ML pipelines, analytics APIs, Agent orchestrator) and a modern **React frontend** (interactive time-series monitoring, anomaly triage board, and Copilot conversational drawer).

## 1. Vision
Commercial and institutional buildings consume over 30% of global electricity, with an estimated 15% to 30% wasted due to suboptimal setpoints, undetected equipment faults (e.g., HVAC running off-hours, chiller degradation, damper leaks), and lack of actionable insights for facility managers.

**EcoTrack** transforms passive energy monitoring into an active, intelligent intelligence layer. By combining high-precision machine learning forecasting (XGBoost) with unsupervised anomaly detection (Isolation Forest), EcoTrack flags irregular consumption patterns in real time. Rather than presenting cryptic numerical alarms, EcoTrack’s conversational LLM Agent contextualizes anomalies against operational schedules, weather conditions, and historical baselines—delivering plain-language diagnostic reports and automated, high-ROI operational recommendations to building managers and facility engineers.

## 2. Target User

### 2.1 Jobs To Be Done (JTBD)
- **Facility / Operations Engineer**:
  - *Functional*: "Help me pinpoint exactly which zone or chiller subsystem is abnormal right now, explain why it deviated from typical behavior, and tell me which setpoint or actuator to verify."
  - *Contextual*: Needs fast, actionable alerts without sifting through thousands of raw telemetry rows during morning peak shifts.
- **Energy / Sustainability Manager**:
  - *Functional*: "Track building Energy Use Intensity (EUI), forecast electricity demand for peak tariff shaving, and generate compliance/audit-ready monthly energy savings reports."
  - *Emotional*: Wants peace of mind that corporate net-zero targets and budget allocations are met with transparent audit trails.
- **Building General Manager / CFO**:
  - *Financial*: "Quantify actual monetary savings achieved through algorithmic anomaly remediation and reduce operating expenditure (OPEX) by 10–20%."

### 2.2 Non-Users (v1)
- **Individual Residential Tenants / Smart Home Consumers**: v1 is strictly engineered for commercial, industrial, or institutional facilities with centralized HVAC/BMS infrastructure.
- **Direct Autonomous BMS Actuation (Closed-loop Control)**: v1 does not write directly back to BACnet/Modbus control loops without human approval; all control actions remain advisory ("Human-in-the-loop").

### 2.3 Key User Journeys

- **UJ-1: Facility Engineer Diagnoses Overnight Energy Surge via Copilot**
  - **Persona & Context**: Minh, Senior Facilities Engineer for a 12-story commercial tower.
  - **Entry State**: Authenticated on the EcoTrack React web dashboard on Monday morning at 07:30.
  - **Path**:
    1. Minh lands on the EcoTrack overview and notices a high-severity red anomaly badge triggered on Saturday at 23:00.
    2. He clicks on the anomaly pin; the chart isolates the hourly chiller loop consumption showing a 45 kW baseline elevation.
    3. Minh opens the EcoTrack Copilot chat drawer and asks: *"What caused the Saturday 23:00 anomaly in Chiller Loop 2?"*
    4. The LLM Agent queries the anomaly tool and telemetry database, cross-referencing outside air temperature (24°C) and the static schedule (building unoccupied).
  - **Climax**: The Agent responds: *"Chiller Loop 2 ran at 78% capacity between 22:30 and 04:00 despite external temperature dropping to 24°C and building occupancy at 0%. Isolation Forest anomaly score was 0.88. Probable cause: Bypass damper stuck open or manual override left active."*
  - **Resolution**: Minh dispatches a technician to check damper valve V-102. Anomaly status changes from `Open` to `Acknowledged` with a linked diagnostic ticket.
  - **Edge Case**: If telemetry data for weather was missing during that interval, the Agent alerts Minh that outdoor temp was interpolated from secondary station data.

- **UJ-2: Energy Manager Generates Monthly Executive Optimization Report**
  - **Persona & Context**: Sarah, Regional Sustainability Director managing 3 corporate campuses.
  - **Entry State**: Logging in at month-end to prepare board reporting.
  - **Path**:
    1. Sarah navigates to the **Reports & Insights** tab and selects August 2026.
    2. She types a prompt to the LLM Agent: *"Draft executive summary highlighting total kWh saved, top 3 anomaly events resolved, and peak demand charge mitigation."*
    3. The Agent computes baseline delta (XGBoost predicted vs. actual metered consumption) and summarizes resolved anomalies.
  - **Climax**: EcoTrack generates a structured Markdown export demonstrating 14,200 kWh avoided ($2,840 cost avoidance) with clean visualizations.
  - **Resolution**: Sarah exports the signed executive brief with zero manual spreadsheet aggregation.

- **UJ-3: Dispatching 24-Hour Peak Load Forecasting for Tariff Optimization**
  - **Persona & Context**: Operations team planning thermal energy storage (TES) discharge.
  - **Entry State**: Daily automated batch run at 06:00.
  - **Path**:
    1. XGBoost engine ingests scheduled weather forecast (NOAA / OpenWeatherMap) and planned calendar occupancy.
    2. Generates hourly electricity demand curve for 00:00 to 23:59.
    3. Identifies projected peak between 13:00 and 15:30 exceeding peak contract threshold (500 kW).
  - **Climax**: EcoTrack displays a proactive recommendation badge: *"Pre-cool Building Zones A-C from 10:30 to 12:00 to shave 65 kW from expected 14:00 peak."*
  - **Resolution**: Operations team adopts the setpoint adjustment schedule.

## 3. Glossary
- **BMS (Building Management System)**: Computer-based system installed in buildings to control and monitor mechanical and electrical equipment (HVAC, lighting, power systems).
- **EUI (Energy Use Intensity)**: Energy consumed per square meter/foot per year (kWh/m²/year).
- **Baseline Consumption**: Expected electrical load predicted by the XGBoost regression model under given weather, day-of-week, and occupancy conditions.
- **Anomaly Score**: A continuous metric produced by Isolation Forest; values scaled to [0.0, 1.0] where scores > 0.65 represent elevated deviations from nominal behavior.
- **LLM Energy Agent (Copilot)**: ReAct/Tool-calling reasoning system combining Google Gemini / OpenAI models with domain tools (retrieval, metrics calculation, anomaly logs).
- **Sub-metering**: Granular electrical meters dedicated to specific circuits, floors, or equipment (e.g., Chiller Plant, AHU, Lighting, Server Room).
- **Building Data Genome 2 / ASHRAE**: Benchmark open-source multi-building hourly energy consumption and meteorological dataset used for training, validation, and demonstrations.

## 4. Features & Functional Requirements

### 4.1 Data Pipeline & Telemetry Ingestion
**Description:** Ingests, parses, cleanses, and enriches time-series energy telemetry from benchmark datasets (Building Data Genome 2 / ASHRAE) and live REST upload. Realizes UJ-1, UJ-3.

#### FR-1: Multi-source Time-series Ingestion
The system can ingest hourly energy consumption readings (kWh, kW, meter readings) from Building Data Genome 2 / ASHRAE datasets as well as custom CSV uploads via FastAPI endpoints.
**Consequences (testable):**
- Ingestion endpoint validates schema; returns HTTP 201 for valid records and HTTP 422 for malformed payloads.
- Supports batch loading of multi-year building records with automatic timestamp alignment to UTC and local timezone.

#### FR-2: Exogenous Feature Enrichment
The system automatically extracts and joins external meteorological features (Outdoor Air Temperature, Relative Humidity, Wind Speed) and calendar features (Hour of day, Day of week, Holiday indicator, Working hours vs. After-hours).
**Consequences (testable):**
- Missing values (< 2 consecutive hours) are filled via linear interpolation; gaps > 2 hours are flagged with `data_gap_flag = True`.

---

### 4.2 Energy Forecasting Engine (XGBoost)
**Description:** Supervised gradient boosting regression pipeline providing dynamic baselines and multi-step forward consumption forecasts. Realizes UJ-2, UJ-3.

#### FR-3: Time-Series Training & Cross-Validation Pipeline
The system shall train an XGBoost regressor using expanding window or TimeSeriesSplit cross-validation, preventing data leakage across temporal boundaries.
**Consequences (testable):**
- Model evaluation outputs standard metrics: RMSE, MAE, and MAPE (Mean Absolute Percentage Error).
- Model artifact checkpoint (`xgboost_energy_v1.joblib`) is saved with metadata containing training timestamps, feature list, and hyperparameters.

#### FR-4: Multi-Horizon Load Forecasting
The system generates 24-hour and 7-day ahead load forecasts at hourly intervals given weather conditions and building operational schedules.
**Consequences (testable):**
- Forecaster API `/api/v1/forecast/predict` responds with array of `{ timestamp, predicted_kwh, lower_bound_95, upper_bound_95 }` within 300ms for a 24-hour horizon.
- The 95% prediction interval is calculated dynamically using quantile regression or residual standard deviation.

#### FR-5: Automated Model Retraining Trigger
The system supports scheduled retraining or drift-triggered retraining when cumulative 7-day MAPE exceeds 15%.
**Consequences (testable):**
- Triggering retraining logs an event in the model registry and updates the active inference model only if new validation score outperforms previous model.

---

### 4.3 Anomaly Detection Engine (Isolation Forest)
**Description:** Unsupervised learning pipeline isolating irregular multivariate energy consumption patterns and assigning severity metrics. Realizes UJ-1, UJ-2.

#### FR-6: Multivariate Anomaly Detection
The system executes an Isolation Forest model accepting multivariate inputs: `actual_kwh`, `residual_error = (actual - predicted_xgboost)`, `outdoor_temp`, `hour`, `is_business_hour`.
**Consequences (testable):**
- Detects point anomalies (instantaneous power spikes) and contextual anomalies (normal power magnitude occurring at abnormal times, such as Sunday 3 AM).
- Produces normalized `anomaly_score` in range `[0.0, 1.0]`, where values > 0.65 represent anomalies.

#### FR-7: Dynamic Thresholding & Severity Classification
The system classifies flagged anomalies into three severity tiers: `Low` (0.65 - 0.75), `Medium` (0.75 - 0.85), `Critical` (> 0.85 or residual deviation > 30% of baseline).
**Consequences (testable):**
- Consecutive anomalous intervals are grouped into a single Anomaly Event with `start_time`, `end_time`, `peak_deviation_kwh`, and `estimated_cost_waste`.
- Suppresses false alarms during scheduled building maintenance windows specified in system configuration.

---

### 4.4 LLM Energy Copilot & Diagnostics Agent
**Description:** Autonomous agent utilizing Cloud API (Google Gemini API / OpenAI) equipped with function-calling capabilities to reason over ML outputs, diagnose root causes, and converse with users in natural language. Realizes UJ-1, UJ-2.

#### FR-8: ReAct Tool Calling Architecture
The LLM Agent is equipped with domain tools:
1. `query_telemetry(meter_id, start_time, end_time)`
2. `get_anomaly_details(anomaly_id)`
3. `get_forecast_comparison(date)`
4. `estimate_waste_cost(anomaly_id, tariff_rate)`
**Consequences (testable):**
- When asked a factual energy query, the agent never hallucinates numbers; it executes the corresponding retrieval tool via Cloud API function calling and quotes exact database values.

#### FR-9: Automated Root Cause Diagnosis (RCA)
When an anomaly event is triggered or selected, the Agent generates an RCA explanation synthesizing operational schedule, weather, and sub-meter correlations.
**Consequences (testable):**
- RCA output contains 3 mandatory sections:
  1. *Observation*: What happened (kWh delta, duration).
  2. *Hypothesis / Probable Cause*: Why it happened (damper failure, baseload drift, thermostat misconfiguration).
  3. *Actionable Recommendation*: Concrete steps for facility crew.

#### FR-10: Conversational Multi-Turn Energy Assistant
The system provides a persistent chat interface supporting Vietnamese and English queries with streaming responses.
**Consequences (testable):**
- Assistant answers domain questions within 2.5s first-token latency using Google Gemini 1.5/2.0 or OpenAI GPT-4o.

---

### 4.5 React Interactive Dashboard (Frontend)
**Description:** Modern, responsive single-page application built with React, Vite, and TailwindCSS to visualize telemetry, forecast curves, anomaly boards, and host the Copilot. Realizes UJ-1, UJ-2, UJ-3.

#### FR-11: Time-Series Visualizer with Forecast Overlays
Dashboard renders interactive charts (Recharts / ECharts) displaying:
- Actual metered load (solid line).
- XGBoost predicted baseline (dashed line) with 95% confidence shaded band.
- Anomaly markers highlighted in amber/red with clickable popovers.
**Consequences (testable):**
- UI updates zoom and aggregation (hourly, daily) smoothly with responsive redraw under 100ms.

#### FR-12: Anomaly Triage Board & Copilot Drawer
A dedicated table/kanban view of detected anomalies with statuses: `New`, `Investigating`, `Resolved`, `False Positive`.
- Clicking "Analyze with Copilot" opens a slide-over chat drawer pre-loaded with the anomaly's diagnostic context.

---

## 5. Non-Goals (Explicit)
- **Direct Closed-Loop Control**: EcoTrack will NOT issue direct write commands to BMS chillers/actuators via BACnet write-property in v1. All recommendations require human verification.
- **Computer Vision / Thermal Camera Integration**: v1 relies strictly on electrical sub-meters and environmental sensors; thermal imaging is out of scope.
- **Tenant Billing & Invoicing Automation**: EcoTrack provides energy consumption analytics and cost estimations, but is not an accounting/invoicing software for commercial tenant billing.
- **Custom Hardware Manufacturing**: EcoTrack is a pure software platform interfacing with standard commercial off-the-shelf (COTS) meters and benchmark time-series datasets.

## 6. MVP Scope

### 6.1 In Scope for MVP
- **Data Ingestion**: Integrated Building Data Genome 2 / ASHRAE hourly dataset loader + CSV upload API.
- **Forecasting Model**: Pre-trained and fine-tunable **XGBoost** regression model for next-24-hour hourly load forecasting.
- **Anomaly Detection**: **Isolation Forest** pipeline with tunable contamination factor and dynamic residual thresholding.
- **Backend**: **FastAPI** service exposing REST endpoints for metrics, predictions, anomalies, and streaming Copilot chat.
- **Frontend**: **React** (Vite + TailwindCSS + Lucide Icons + Recharts) providing a professional building energy cockpit.
- **LLM Agent**: **Google Gemini API / OpenAI** integration with 4 core domain tools.
- Dual-language support: Vietnamese and English.

### 6.2 Out of Scope for MVP (Deferred to v2)
- Real-time native BACnet/IP and Modbus TCP active polling daemons.
- Multi-tenant cloud SaaS provisioning with role-based access control (RBAC).
- Automated SMS/WhatsApp alert dispatching.

## 7. Success Metrics & Quality Rubric

### 7.1 Primary Metrics
- **SM-1: Forecast Accuracy (XGBoost)**: Mean Absolute Percentage Error (MAPE) ≤ **10.0%** across test building validation datasets. (Validates FR-3, FR-4).
- **SM-2: Anomaly Detection Precision & Recall**: True anomaly detection rate ≥ **85%** with False Positive Rate (FPR) ≤ **12%** based on benchmark labeled anomalies. (Validates FR-6, FR-7).
- **SM-3: Diagnostics Actionability (LLM Agent)**: ≥ **80%** of generated diagnostic recommendations rated as "technically valid and helpful" by facility engineering evaluation. (Validates FR-9, FR-10).

### 7.2 Secondary Metrics
- **SM-4: Time to Detect & Diagnose (TTD/TTD)**: Average time taken by a facility engineer to pinpoint an anomaly reduced from 4 hours to < 10 minutes. (Validates UJ-1, FR-11, FR-12).
- **SM-5: API Response Latency**: 95th percentile response time < 300ms for data/forecast queries; < 2.5s first-chunk streaming response for LLM queries.

### 7.3 Counter-Metrics (Do Not Optimize)
- **SM-C1: Alert Quantity vs. Alert Fatigue**: Do NOT maximize total anomalies flagged. Alert volume must remain bounded (< 5 high-priority alerts per building per day) to prevent engineer alert fatigue. Counterbalances SM-2.
- **SM-C2: Agent Verbosity**: Do NOT maximize length of LLM output. Agent answers must be concise, bulleted, and direct; excessive prose slows operational triage.

## 8. Cross-Cutting Non-Functional Requirements (NFRs)
- **NFR-1 (Performance)**: Telemetry processing pipeline must process 10,000 sensor readings in < 2 seconds.
- **NFR-2 (Privacy & Security)**: API keys (Gemini/OpenAI) stored strictly in server-side `.env`; client frontend never has direct access to LLM credentials.
- **NFR-3 (Extensibility)**: Model interfaces follow standard Scikit-learn estimator conventions (`fit`, `predict`, `score`).
- **NFR-4 (Observability)**: All Agent tool calls, execution latencies, and token counts logged.

## 9. Open Questions (Status: Resolved / Active)
1. ~~**OQ-1 (Resolved)**: Which primary dataset will be used?~~ -> **Building Data Genome 2 / ASHRAE hourly dataset**.
2. ~~**OQ-2 (Resolved)**: Which LLM provider?~~ -> **Cloud API (Google Gemini API / OpenAI) for tool calling speed**.
3. ~~**OQ-3 (Resolved)**: UI architecture?~~ -> **Decoupled FastAPI backend + React frontend**.
4. **OQ-4 (Active)**: Default electricity tariff rate for cost waste calculation (e.g., standard EVN commercial peak/off-peak rate: ~3,100 VNĐ/kWh vs. Flat $0.15/kWh)?

## 10. Assumptions Index
- `[CONFIRMED: User Decision 2026-09-23]` MVP uses Building Data Genome 2 / ASHRAE benchmark hourly dataset.
- `[CONFIRMED: User Decision 2026-09-23]` LLM Copilot uses Cloud API (Google Gemini API / OpenAI) with JSON tool calling.
- `[CONFIRMED: User Decision 2026-09-23]` Frontend is a standalone React single-page app interacting via REST API with FastAPI backend.

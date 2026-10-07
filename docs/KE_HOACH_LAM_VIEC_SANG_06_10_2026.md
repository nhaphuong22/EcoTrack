# DỰ ÁN ECOTRACK — KẾ HOẠCH LÀM VIỆC & PHÂN CÔNG NHIỆM VỤ
## Phiên làm việc: Sáng Thứ Ba, ngày 06/10/2026 (08:30 – 11:30)
**Điều phối dự án:** Nhã Phương (Project Lead & Data Pipeline Lead)  
**Mục tiêu cốt lõi:** Bắt đầu tăng tốc Chặng 2 (Ghép nối Fullstack, Nâng cấp Copilot & Đo đạc số liệu NCKH).

---

## ⏰ I. LỊCH TRÌNH CHI TIẾT THEO KHUNG GIỜ

| Thời gian | Hoạt động chính | Nội dung & Yêu cầu |
| :---: | :--- | :--- |
| **08:30 – 08:50** | **Daily Standup Toàn Nhóm** | • Họp nhanh qua Google Meet / Discord (15–20 phút).<br>• Cả 5 thành viên chạy lệnh đồng bộ code mới nhất từ nhánh `main`: `git pull origin main`.<br>• Khởi động hệ thống bằng 1 lệnh duy nhất: `npm run dev` để kiểm tra môi trường chạy trơn tru.<br>• Làm rõ các điểm kết nối (API contracts, schema dữ liệu) giữa Frontend - Backend - ML. |
| **08:50 – 11:00** | **Tập trung Kỹ thuật (Deep Work)** | • Từng thành viên tạo branch riêng theo quy tắc: `feature/<tên>-<nhiệm-vụ>`.<br>• Tập trung thực hiện các nhiệm vụ được phân công chi tiết ở Mục II.<br>• Luôn duy trì song song 2 đường ray: **Track Kỹ thuật hệ thống** và **Track Báo cáo NCKH**. |
| **11:00 – 11:30** | **Sync Code, Review & Nghiệm thu Mini** | • Chạy lại bộ kiểm thử tự động: `pytest backend`.<br>• Commit code sạch và đẩy branch lên GitHub, mở Pull Request vào `develop`.<br>• Tổng kết sản phẩm bàn giao của ca sáng và chốt kế hoạch ca chiều. |

---

## 👥 II. NHIỆM VỤ CHI TIẾT PHÂN CÔNG CHO 5 THÀNH VIÊN

### 1. 🌾 PHƯƠNG — Data Pipeline Lead
* **Track Hệ thống (Kỹ thuật):**
  * Kiểm tra việc đồng bộ dữ liệu từ script `extract_office_building.py` trực tiếp vào bảng `meter_readings` của PostgreSQL trong Docker.
  * Tinh chỉnh script `backend/src/data_pipeline/stream_worker.py` để giả lập đẩy dữ liệu viễn trắc chuỗi thời gian (mỗi 5 giây đẩy 1 bản ghi mới) vào CSDL phục vụ demo thời gian thực.
* **Track Nghiên cứu Khoa học (NCKH):**
  * Soạn thảo bản thảo **Mục III.1 (Data Engineering & BDG2 Features)** trong tài liệu [`docs/ECOTRACK_SCIENTIFIC_REPORT_DRAFT.md`](./ECOTRACK_SCIENTIFIC_REPORT_DRAFT.md).
  * Xuất bảng số liệu thống kê mô tả (Mean, Variance, phân bổ giờ cao điểm/thấp điểm) của tập dữ liệu tòa nhà văn phòng BDG2.
* **📦 Sản phẩm bàn giao lúc 11:30:**
  * Script `stream_worker.py` hoạt động mượt mà với PostgreSQL.
  * File nháp nội dung Mục III.1 nộp vào tài liệu báo cáo.

---

### 2. ⚡ QUÂN — AI/ML Lead
* **Track Hệ thống (Kỹ thuật):**
  * Triển khai hàm tính toán **Dải khoảng tin cậy 95% (Confidence Interval: $\hat{y} \pm 1.96 \times \sigma$)** trong endpoint `/api/v1/forecast/predict-24h` để cung cấp biên trên / biên dưới cho Frontend vẽ dải bóng mờ.
  * Tối ưu hàm suy luận XGBoost và Isolation Forest đảm bảo độ trễ suy luận (Inference Latency) $< 20\text{ms/sample}$.
* **Track Nghiên cứu Khoa học (NCKH):**
  * Chuẩn bị bảng số liệu so sánh đối chuẩn (Baseline Comparison) giữa XGBoost với Random Forest và Linear Regression (đo trên tập test BDG2).
  * Viết nháp **Mục III.2 & III.3** (Thiết kế mô hình dự báo XGBoost và phát hiện dị thường Isolation Forest kết hợp phân tích độ lệch dư Residuals).
* **📦 Sản phẩm bàn giao lúc 11:30:**
  * Router forecast trả về kèm trường `confidence_interval_95`.
  * Bảng số liệu MAPE, RMSE, R² của XGBoost so với baselines.

---

### 3. 🛠️ TUẤN — Backend & Data Services Lead
* **Track Hệ thống (Kỹ thuật):**
  * Xây dựng API quản lý vòng đời trạng thái sự cố dị thường:
    * `PATCH /api/v1/anomalies/{anomaly_id}/status`: Cập nhật trạng thái sự cố giữa `OPEN` ➔ `ACKNOWLEDGED` ➔ `RESOLVED`.
    * Cập nhật trực tiếp vào bảng `anomaly_events` trong CSDL PostgreSQL.
  * Thử nghiệm cài đặt bộ đệm In-memory Caching (TTL Cache / Redis) tại router `backend/src/api/routers/energy.py` để giảm tải DB cho các truy vấn chuỗi thời gian, hướng tới độ trễ $< 50\text{ms}$.
* **Track Nghiên cứu Khoa học (NCKH):**
  * Viết nháp **Mục V (Hạ tầng dịch vụ & Hiệu năng API Backend)** trong bài báo khoa học.
  * Chuẩn bị kịch bản đo đạc độ trễ API (Latency benchmarks) khi chịu tải đồng thời (Concurrent requests).
* **📦 Sản phẩm bàn giao lúc 11:30:**
  * Endpoint `PATCH /anomalies/{id}/status` hoàn chỉnh kèm unit test trong `tests/`.

---

### 4. 🧠 HOÀNG — AI Agent & LLM Lead
* **Track Hệ thống (Kỹ thuật):**
  * Nâng cấp [`CopilotOrchestrator`](../backend/src/agent/orchestrator.py) lên cơ chế **Native Function Calling** chuẩn (Google Gemini API / OpenAI API).
  * Kết nối lưu vết lịch sử trò chuyện vào bảng **`conversations`** đã khởi tạo trong CSDL PostgreSQL.
  * Thiết lập cơ chế **Context Injection**: Khi nhận truy vấn có kèm `anomaly_id`, Agent tự động nạp thông tin sự cố (chỉ số kW bất thường, mức độ nghiêm trọng, thời điểm) vào prompt để chẩn đoán nguyên nhân gốc (Root Cause Analysis - RCA).
* **Track Nghiên cứu Khoa học (NCKH):**
  * Chạy kịch bản kiểm nghiệm thực tế trên bộ **4 Case Study sự cố** bằng lệnh: `python backend/experiments/run_benchmark.py`.
  * Kiểm tra file log tự động sinh ra tại [`backend/experiments/logs/agent_eval_logs.jsonl`](../backend/experiments/logs/agent_eval_logs.jsonl) và thống kê tỷ lệ chọn đúng tool.
* **📦 Sản phẩm bàn giao lúc 11:30:**
  * Module Copilot có khả năng nhận Context Injection sự cố.
  * Bộ log thực nghiệm đầu tiên được ghi nhận vào file `agent_eval_logs.jsonl`.

---

### 5. 🎨 NHÂN — Frontend Lead & Project Coordinator
* **Track Hệ thống (Kỹ thuật):**
  * Nâng cấp biểu đồ chuỗi thời gian Recharts trên giao diện Dashboard:
    * Vẽ **dải màu bóng mờ khoảng tin cậy 95%** bao quanh đường dự báo tải theo dữ liệu từ API của Quân.
    * Ghim **chấm đỏ cảnh báo nhấp nháy** tại đúng các mốc thời gian xảy ra sự cố điện năng.
  * Tích hợp tương tác 2 chiều: Khi người dùng nhấp vào nút *"Chẩn đoán bằng Copilot"* tại thẻ sự cố trong bảng Anomaly Table, giao diện tự động trượt mở **Copilot Drawer** và nạp sẵn câu hỏi chẩn đoán sự cố đó.
* **Track Quản trị & NCKH:**
  * Thiết lập project **Overleaf** theo định dạng IEEE Conference / Springer và phân quyền truy cập cho cả 5 thành viên.
  * Thiết kế sơ đồ kiến trúc hệ thống tổng thể EcoTrack dưới dạng đồ họa vector sắc nét để đưa vào báo cáo.
* **📦 Sản phẩm bàn giao lúc 11:30:**
  * Giao diện React hiển thị chấm cảnh báo sự cố trên biểu đồ.
  * Link project Overleaf sẵn sàng cho cả nhóm cùng biên tập bài báo.

---

## 📌 III. QUY TẮC LÀM VIỆC VÀ NGUYÊN TẮC BẢO TOÀN DỰ ÁN

1. **Khởi động dự án thống nhất:**
   Chỉ cần 1 lệnh duy nhất tại thư mục gốc:
   ```powershell
   npm run dev
   ```
2. **Quy tắc Git Workflow:**
   * Không commit trực tiếp vào `main`.
   * Luôn tạo branch từ `develop`: `git checkout -b feature/<tên-thành-viên>-<tính-năng>`.
   * Chạy kiểm thử nội bộ trước khi tạo Pull Request:
     ```powershell
     pytest backend
     ```
3. **Ý thức Nghiên cứu Khoa học (NCKH):**
   * Mọi thao tác gọi API Copilot đều được tự động lưu log vào `backend/experiments/logs/agent_eval_logs.jsonl` qua module `experiment_logger.py`.
   * Các số liệu đo đạc (độ trễ, tỉ lệ chính xác, MAPE) đều là bằng chứng thực nghiệm trực tiếp để hoàn thành bản thảo [`docs/ECOTRACK_SCIENTIFIC_REPORT_DRAFT.md`](./ECOTRACK_SCIENTIFIC_REPORT_DRAFT.md) trước hạn bảo vệ **15/12/2026**.

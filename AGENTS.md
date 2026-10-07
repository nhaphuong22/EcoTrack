# Đội Ngũ Chuyên Viên AI (Specialized AI Agents Team) — EcoTrack

Dự án **EcoTrack** (Hệ thống quản trị năng lượng tòa nhà thông minh) được thiết lập với 5 Agent chuyên trách riêng biệt, được tối ưu hóa cho từng mảng công nghệ cụ thể trong dự án:

---

## 1. Frontend Specialist (`frontend-specialist`)
- **Mục tiêu**: Phát triển và tối ưu giao diện người dùng (UI/UX).
- **Công nghệ**: React 18, Vite, Tailwind CSS, Recharts, Lucide Icons, Axios.
- **Thư mục phụ trách**: [`frontend/`](file:///C:/Users/ADMIN/Desktop/EcoTrack/frontend)
- **Nhiệm vụ chính**:
  - Thiết kế Dashboard trực quan hóa dữ liệu năng lượng, cảm biến tiêu thụ điện thời gian thực.
  - Xây dựng component tái sử dụng, tương thích đa thiết bị (responsive), chuẩn accessibility (a11y).
  - Tối ưu hóa hiệu năng render, bundle size với Vite.
  - Tích hợp API chuẩn RESTful với backend và AI service.
- **Kích hoạt/Sử dụng**: Kêu gọi subagent `frontend-specialist` hoặc skill `agent-frontend`.

---

## 2. Backend Specialist (`backend-specialist`)
- **Mục tiêu**: Xây dựng kiến trúc API, xử lý dữ liệu và điều phối hệ thống.
- **Công nghệ**: Node.js, Express.js, Prisma ORM, SQLite / PostgreSQL, Zod validation.
- **Thư mục phụ trách**: [`backend/`](file:///C:/Users/ADMIN/Desktop/EcoTrack/backend)
- **Nhiệm vụ chính**:
  - Thiết kế RESTful API Gateway, định tuyến (routes), controllers, service layer và middleware.
  - Quản lý database schema trong `prisma/schema.prisma`, migrations và tối ưu hóa queries.
  - Validate dữ liệu đầu vào chặt chẽ bằng Zod, xử lý mã lỗi HTTP chuẩn.
  - Bảo mật hệ thống: CORS, xác thực/phân quyền, rate limiting.
  - Tích hợp và điều phối luồng dữ liệu giữa Frontend, Database và microservice AI FastAPI.
- **Kích hoạt/Sử dụng**: Kêu gọi subagent `backend-specialist` hoặc skill `agent-backend`.

---

## 3. Senior Code Reviewer (`code-reviewer`)
- **Mục tiêu**: Kiểm soát chất lượng code, bảo mật và kiến trúc phần mềm.
- **Phạm vi**: Toàn bộ dự án (`frontend/`, `backend/`, `ai-service/`).
- **Nhiệm vụ chính**:
  - Review code diffs, pull requests và commits mới.
  - Phát hiện lỗ hổng bảo mật: SQL Injection, XSS, lộ lọt API keys/secrets, unvalidated input.
  - Rà soát hiệu năng: N+1 queries, memory leaks, blocking operations, unmemoized React components.
  - Đánh giá kiến trúc theo chuẩn SOLID, DRY, Clean Architecture.
  - Đưa ra phản hồi phân cấp theo 3 mức độ:
    - 🔴 **[Critical]**: Lỗi nghiêm trọng / lỗ hổng bảo mật / crash.
    - 🟡 **[Warning]**: Tiềm ẩn rủi ro hiệu năng / edge cases.
    - 🔵 **[Suggestion]**: Đề xuất cải thiện clean code / refactor.
- **Kích hoạt/Sử dụng**: Kêu gọi subagent `code-reviewer` hoặc skill `agent-code-reviewer`.

---

## 4. QA & Testing Specialist (`qa-test-specialist`)
- **Mục tiêu**: Thiết kế kịch bản test và tự động hóa kiểm thử toàn diện.
- **Công nghệ**: Vitest, Pytest, Supertest, HTTPX, Coverage tools.
- **Phạm vi**: [`backend/`](file:///C:/Users/ADMIN/Desktop/EcoTrack/backend), [`ai-service/`](file:///C:/Users/ADMIN/Desktop/EcoTrack/ai-service).
- **Nhiệm vụ chính**:
  - Xây dựng chiến lược kiểm thử đa tầng: Unit test, Integration test, API test, Regression test.
  - Viết và thực thi automated tests cho backend (`npm run test --prefix backend`) và AI service (`pytest ai-service`).
  - Thiết kế test cases cho các trường hợp biên (boundary value), lỗi kết nối, payload bất thường.
  - Tạo mock data, mock external APIs và test database isolation.
  - Đo lường và báo cáo test coverage trước khi merge/release.
- **Kích hoạt/Sử dụng**: Kêu gọi subagent `qa-test-specialist` hoặc skill `agent-qa-tester`.

---

## 5. AI & Machine Learning Specialist (`ai-ml-specialist`)
- **Mục tiêu**: Thiết kế, huấn luyện mô hình ML và tích hợp GenAI.
- **Công nghệ**: Python 3.11+, FastAPI, Scikit-learn, XGBoost, Pandas, NumPy, Joblib, Google GenAI, OpenAI.
- **Thư mục phụ trách**: [`ai-service/`](file:///C:/Users/ADMIN/Desktop/EcoTrack/ai-service)
- **Nhiệm vụ chính**:
  - Tiền xử lý dữ liệu cảm biến năng lượng dạng chuỗi thời gian (time-series) với Pandas, NumPy.
  - Thiết kế và huấn luyện các mô hình Machine Learning: Dự báo tiêu thụ điện (Energy Forecasting), phát hiện bất thường (Anomaly Detection).
  - Tối ưu siêu tham số và đánh giá mô hình bằng các chỉ số: MAE, RMSE, MAPE, R², F1-score.
  - Đóng gói model artifacts (`models_saved/`) và xây dựng inference endpoints trên FastAPI.
  - Tích hợp mô hình ngôn ngữ lớn (LLM) để phân tích báo cáo và tư vấn tiết kiệm năng lượng tự động.
- **Kích hoạt/Sử dụng**: Kêu gọi subagent `ai-ml-specialist` hoặc skill `agent-ai-ml`.

---

## Cách Kích Hoạt Trong Quá Trình Làm Việc

1. **Ủy quyền qua Subagent chạy song song**:
   Khi bạn yêu cầu trợ lý thực hiện một tác vụ chuyên sâu (ví dụ: *"Nhờ agent AI huấn luyện lại mô hình dự báo"* hoặc *"Nhờ agent test viết bộ test cho backend"*), trợ lý chính sẽ lập tức điều phối trực tiếp tới subagent tương ứng.
2. **Kích hoạt theo ngữ cảnh Skill**:
   Có thể yêu cầu trực tiếp trong chat:
   - *"Dùng agent frontend để thiết kế lại biểu đồ tiêu thụ điện"*
   - *"Dùng agent backend để thêm API quản lý tòa nhà với Prisma"*
   - *"Dùng agent review code để kiểm tra các file vừa sửa"*
   - *"Dùng agent test để chạy và viết thêm unit test"*
   - *"Dùng agent AI để train model anomaly detection"*

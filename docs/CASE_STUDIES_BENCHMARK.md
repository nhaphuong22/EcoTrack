# ECOTRACK: DANH MỤC CASE STUDY SỰ CỐ NĂNG LƯỢNG MẪU (GROUND TRUTH BENCHMARK)
## TÀI LIỆU PHỤC VỤ THỰC NGHIỆM ĐÁNH GIÁ CHẨN ĐOÁN FDD & BÀI BÁO KHOA HỌC

---

Tài liệu này lưu trữ chi tiết **4 tình huống sự cố điển hình (Case Studies)** được trích xuất từ dữ liệu công trình chuẩn **Building Data Genome 2 (BDG2 - Tòa nhà `Hog_office_Betsy`)**, kết hợp chuẩn chẩn đoán lỗi thiết bị HVAC của **ASHRAE Guideline 36** và **ASHRAE Great Energy Predictor III**.

Bộ dữ liệu này đóng vai trò là **Ground Truth (Nhãn chuẩn chuyên gia)** để:
1. **Kiểm thử nghiệm thu hệ sinh thái EcoTrack** trước hội đồng bảo vệ đồ án môn học (Review ngày 15/12/2026).
2. **Đánh giá định lượng năng lực tác tử LLM Agent** trong bài báo NCKH (Độ chính xác chọn Tool, độ chính xác chẩn đoán nguyên nhân gốc, độ bám sát dữ liệu thực tế và tính khả thi của giải pháp khuyến nghị).

---

## 1. TỔNG QUAN 4 CASE STUDY

| Mã sự cố | Tên kịch bản | Hệ thống phụ trách | Mức độ nghiêm trọng | Lãng phí ước tính (kWh) |
| :--- | :--- | :--- | :--- | :--- |
| **CS-01** | Kẹt van bypass chiller xuyên đêm cuối tuần | HVAC Chiller Plant & AHU | **CRITICAL** | +65.5 kWh/h (~390 kWh) |
| **CS-02** | Xung đột biến phụ tải đỉnh giờ cao điểm EVN | HVAC Compressor & Tháp giải nhiệt | **CRITICAL** | +85.0 kWh/h (~255 kWh) |
| **CS-03** | Rò rỉ phụ tải nền (FCU và đèn quên tắt) | Mạch chiếu sáng & Fan Coil Units | **HIGH** | +45.0 kWh/h (~180 kWh) |
| **CS-04** | Sai lệch lịch trình làm mát sớm (Pre-cooling) | Bộ lập lịch BMS trung tâm | **HIGH** | +50.0 kWh/h (~100 kWh) |

---

## 2. CHI TIẾT TỪNG KỊCH BẢN THỰC NGHIỆM

### 🔴 Case Study CS-01: Kẹt van bypass Chiller xuyên đêm cuối tuần (Off-Hours Cooling Surge)

#### A. Ngữ cảnh vận hành & Dữ liệu viễn thám
- **Thời gian ghi nhận**: Thứ Bảy, 23:00 (Building Unoccupied - Tòa nhà không có người).
- **Điều kiện thời tiết**: Nhiệt độ ngoài trời mát $24.2^\circ\text{C}$, độ ẩm $78.5\%$.
- **Dữ liệu đo đạc**:
  - Tiêu thụ thực tế: **$107.5\text{ kWh}$**
  - Baseline dự báo (XGBoost): **$42.0\text{ kWh}$**
  - Độ lệch dư (Residual): **$+65.5\text{ kWh}$** ($+156\%$ so với baseline)
  - Anomaly Score (Isolation Forest): **$0.88$** $\rightarrow$ Phân loại: `CRITICAL`.

#### B. Cơ chế vật lý & Nguyên nhân gốc rễ (Ground Truth RCA)
Van bypass damper tại tháp giải nhiệt/buồng AHU tầng 12 bị kẹt ở trạng thái mở $78\%$ do hỏng actuator hoặc do kỹ thuật viên ca trước gạt sang chế độ `Manual Override` nhưng quên hoàn trả về `Auto`. Do đó, chiller liên tục duy trì chu trình bơm giải nhiệt dù tòa nhà đã tắt tải lạnh.

#### C. Hành động khắc phục chuẩn (Mitigation Actions)
1. Cử kỹ thuật viên kiểm tra cơ khí và actuator van damper gió tươi/bypass tại buồng kỹ thuật AHU tầng 12.
2. Hủy trạng thái `Manual Override` trên bộ điều khiển DDC / giao diện BMS trung tâm.
3. Thiết lập chốt an toàn (interlock) tự động ngắt nguồn chiller khi lịch trình tòa nhà chuyển sang trạng thái Unoccupied.

#### D. Kịch bản câu hỏi kiểm thử Agent (Test Prompts)
- *"Giải thích nguyên nhân sự cố bất thường lúc 23h đêm thứ Bảy?"*
- *"Tại sao lượng điện chiller tăng đột biến ngoài giờ vận hành?"*
- *"Sự cố đêm thứ Bảy gây thiệt hại bao nhiêu tiền và cách xử lý ra sao?"*

---

### 🔴 Case Study CS-02: Đột biến phụ tải đỉnh giờ cao điểm (Peak Cooling Surge)

#### A. Ngữ cảnh vận hành & Dữ liệu viễn thám
- **Thời gian ghi nhận**: Chiều thứ Ba, 14:00 (Giờ cao điểm hành chính & cao điểm giá điện EVN).
- **Điều kiện thời tiết**: Nắng nóng gay gắt, nhiệt độ ngoài trời đạt đỉnh $34.8^\circ\text{C}$, độ ẩm $65.0\%$.
- **Dữ liệu đo đạc**:
  - Tiêu thụ thực tế: **$265.0\text{ kWh}$**
  - Baseline dự báo (XGBoost): **$180.0\text{ kWh}$**
  - Độ lệch dư (Residual): **$+85.0\text{ kWh}$** ($+47\%$ so với baseline)
  - Anomaly Score (Isolation Forest): **$0.92$** $\rightarrow$ Phân loại: `CRITICAL`.

#### B. Cơ chế vật lý & Nguyên nhân gốc rễ (Ground Truth RCA)
Máy nén điều hòa trung tâm bị hiện tượng chu kỳ ngắn (short cycling) do thiết lập dải nhiệt độ chênh lệch (deadband) quá hẹp, cộng hưởng với phụ tải nhiệt mặt trời đạt đỉnh khiến các máy nén đồng loạt đóng ngắt liên tục ở dòng khởi động lớn. Nguy cơ vi phạm công suất hợp đồng đăng ký với công ty điện lực.

#### C. Hành động khắc phục chuẩn (Mitigation Actions)
1. Tạm thời nâng dải setpoint nhiệt độ điều hòa từ $23.5^\circ\text{C}$ lên $25.0^\circ\text{C}$ trong khung giờ 13:00 - 15:30.
2. Kích hoạt xả lạnh từ bể tích trữ nhiệt (nếu có) hoặc áp dụng làm mát sớm (Pre-cooling) từ 11:30 sáng.
3. Kiểm tra áp suất gas và hiệu chỉnh lại bộ trễ thời gian đóng cắt (anti-recycle timer) của máy nén.

#### D. Kịch bản câu hỏi kiểm thử Agent (Test Prompts)
- *"Tại sao chiều thứ Ba phụ tải điện lại tăng đột biến vượt đỉnh dự báo?"*
- *"Đề xuất giải pháp giảm phụ tải đỉnh giờ cao điểm chiều nay?"*

---

### 🟠 Case Study CS-03: Rò rỉ phụ tải nền do quên tắt thiết bị cuối tuần (Baseload Leakage)

#### A. Ngữ cảnh vận hành & Dữ liệu viễn thám
- **Thời gian ghi nhận**: Rạng sáng Chủ nhật, 03:00 (Building Unoccupied).
- **Điều kiện thời tiết**: Ban đêm mát mẻ, nhiệt độ ngoài trời $23.5^\circ\text{C}$.
- **Dữ liệu đo đạc**:
  - Tiêu thụ thực tế: **$80.0\text{ kWh}$**
  - Baseline dự báo (XGBoost): **$35.0\text{ kWh}$**
  - Độ lệch dư (Residual): **$+45.0\text{ kWh}$** ($+128\%$ so với baseline phụ tải nền)
  - Anomaly Score (Isolation Forest): **$0.74$** $\rightarrow$ Phân loại: `HIGH`.

#### B. Cơ chế vật lý & Nguyên nhân gốc rễ (Ground Truth RCA)
Nhân sự một doanh nghiệp thuê tầng 5 và 6 tổ chức làm việc thêm giờ (overtime) tối thứ Bảy nhưng khi ra về đã không tắt hệ thống đèn huỳnh quang/LED văn phòng và 12 dàn quạt lạnh cục bộ (FCU), khiến phụ tải nền duy trì ở mức cao suốt đêm.

#### C. Hành động khắc phục chuẩn (Mitigation Actions)
1. Gửi lệnh cắt điện cưỡng bức cụm phụ tải chiếu sáng/ổ cắm tầng 5-6 thông qua rơ-le điều khiển tủ điện tầng.
2. Đề xuất ban quản lý trang bị cảm biến hồng ngoại thụ động (PIR motion sensor) tự ngắt điện sau 20 phút không chuyển động.

---

### 🟠 Case Study CS-04: Lập lịch làm mát sớm không hiệu quả (Pre-Cooling Scheduling Inefficiency)

#### A. Ngữ cảnh vận hành & Dữ liệu viễn thám
- **Thời gian ghi nhận**: Sáng thứ Hai, 08:30 - 09:30 (Morning Ramp-up).
- **Dữ liệu đo đạc**:
  - Tiêu thụ thực tế: **$195.0\text{ kWh}$** vs Baseline **$145.0\text{ kWh}$** (Chênh lệch $+50\text{ kWh}$).
  - Anomaly Score: **$0.71$** $\rightarrow$ Phân loại: `HIGH`.

#### B. Cơ chế vật lý & Nguyên nhân gốc rễ (Ground Truth RCA)
Hệ thống bật đồng loạt 100% công suất các dàn lạnh vào đúng thời điểm 08:30 khi nhân viên bắt đầu tới văn phòng, tạo ra một đỉnh phụ tải tức thời rất dốc (steep ramp rate) gây căng thẳng cho trạm biến áp và gia tăng chi phí theo công suất cực đại (kVA demand charge).

#### C. Hành động khắc phục chuẩn (Mitigation Actions)
Tích hợp thuật toán dự báo phụ tải XGBoost 24h vào bộ lập lịch tự động: Khởi động so le (Staggered start) từ 07:15 sáng để tận dụng làm mát tích trữ nhiệt trước khi nhân viên vào phòng.

---

## 3. CÁCH SỬ DỤNG BỘ CASE STUDY NÀY

1. **Khi Review Đồ án Môn học (15/12/2026)**:
   - Mở màn hình Dashboard EcoTrack.
   - Nhấp vào điểm sự cố CS-01 hoặc CS-02 trên biểu đồ.
   - Bật Copilot Drawer, bấm Quick Prompt hoặc gõ đúng câu hỏi trong kịch bản.
   - Cho hội đồng thấy Copilot phân tích đúng nguyên nhân vật lý và đưa ra khuyến nghị thực tế.
2. **Khi Viết Bài báo NCKH (Mục Section V - Case Studies)**:
   - Trích dẫn trực tiếp bảng so sánh Baseline vs Actual vs Residual của 2 trong 4 trường hợp này.
   - Trình bày dạng hộp thoại minh họa (Figure: Dialogue interaction between Facility Engineer and EcoTrack Copilot).

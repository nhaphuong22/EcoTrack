---
title: Hướng dẫn Vận hành Trạm Chiller Giải nhiệt nước (Water-cooled Chiller Plant)
source: ASHRAE Guideline 22 & Cẩm nang Vận hành BEMS EcoTrack
---

# Quy trình Vận hành Trạm Chiller Giải nhiệt nước Hiệu quả cao

## 1. Trình tự khởi động an toàn (Startup Sequence)
Để tránh hiện tượng đóng băng bình bay hơi hoặc quá tải áp suất ngưng tụ, trình tự khởi động bắt buộc phải tuân thủ:
1. Mở van cô lập nước lạnh và van nước giải nhiệt của tổ máy chiller cần chạy.
2. Bật tháp giải nhiệt (Cooling Tower) và quạt tháp.
3. Khởi động bơm nước giải nhiệt (Condenser Water Pump - CWP) và xác nhận có dòng chảy qua công tắc dòng (Flow Switch).
4. Khởi động bơm nước lạnh (Chilled Water Pump - CHWP) và xác nhận có dòng chảy.
5. Sau khi lưu lượng nước ổn định tối thiểu 2 phút, phát lệnh khởi động máy nén Chiller.

## 2. Trình tự dừng máy (Shutdown Sequence)
1. Phát lệnh dừng máy nén Chiller trước.
2. Duy trì bơm nước lạnh và bơm giải nhiệt chạy thêm từ 3 đến 5 phút để lấy hết nhiệt dư trong giàn bay hơi và ngưng tụ.
3. Dừng quạt tháp giải nhiệt, bơm giải nhiệt và bơm nước lạnh.
4. Đóng các van cô lập tự động.

## 3. Chỉ số đánh giá hiệu năng (KPI Vận hành)
- **Hiệu suất cụm chiller (kW/RT)**:
  - Dưới $0.65 \text{ kW/RT}$: Rất tốt (Tối ưu).
  - Từ $0.65 - 0.85 \text{ kW/RT}$: Trung bình.
  - Trên $0.85 \text{ kW/RT}$: Kém, cần kiểm tra cáu cặn bình ngưng, thiếu gas hoặc cảm biến sai lệch.

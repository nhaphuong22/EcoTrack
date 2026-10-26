---
title: Chiến lược Tối ưu hóa Nhiệt độ Nước lạnh Cung cấp (CHWST Reset Strategy)
source: ASHRAE Guideline 36 - High-Performance Sequences of Operation
---

# Chiến lược Điều khiển Tái lập Nhiệt độ Nước lạnh (Chilled Water Supply Temperature Reset)

## 1. Nguyên lý vận hành
- Thông thường trạm Chiller được cài đặt nhiệt độ nước lạnh cấp cố định là $6.7^\circ\text{C} - 7.0^\circ\text{C}$ (thiết kế cho phụ tải đỉnh mùa hè).
- Tuy nhiên, trong hơn $85\%$ thời gian vận hành trong năm, phụ tải thực tế của tòa nhà chỉ ở mức một phần tải (Part-load: 40% - 70%).
- Mỗi khi tăng nhiệt độ nước lạnh cấp lên thêm $1^\circ\text{C}$ (ví dụ từ $7^\circ\text{C}$ lên $8.5^\circ\text{C}$), áp suất bay hơi của môi chất tăng lên, giúp máy nén Chiller tiết kiệm từ **$2.5\% - 3.5\%$ điện năng tiêu thụ**.

## 2. Thuật toán điều khiển tự động Trim & Respond
Hệ thống BEMS thu thập độ mở van nước lạnh của tất cả các bộ xử lý không khí (AHU):
- **Giai đoạn Tăng nhiệt độ (Trim)**: Nếu độ mở van lớn nhất của tất cả các AHU trong tòa nhà đều dưới $85\%$ (không có khu vực nào thiếu lạnh), BEMS tự động tăng nhiệt độ đặt nước lạnh thêm $0.2^\circ\text{C}$ mỗi 10 phút (giới hạn tối đa $10.0^\circ\text{C}$).
- **Giai đoạn Giảm nhiệt độ (Respond)**: Nếu có từ 2 AHU trở lên mở van vượt quá $95\%$ liên tục trong 5 phút, BEMS lập tức hạ nhiệt độ đặt nước lạnh xuống $0.5^\circ\text{C}$ để đảm bảo tiện nghi nhiệt.

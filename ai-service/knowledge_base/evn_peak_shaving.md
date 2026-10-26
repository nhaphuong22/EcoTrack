---
title: Hướng dẫn Kỹ thuật Cắt giảm Phụ tải đỉnh (Peak Shaving) và Dịch chuyển Phụ tải (Load Shifting)
source: Hướng dẫn Vận hành Tiết kiệm Năng lượng - EVN & VNEEP
---

# Chiến lược Cắt giảm Phụ tải đỉnh (Peak Shaving) cho Tòa nhà Thương mại

## 1. Bản chất của Cắt giảm Phụ tải đỉnh
- Phụ tải đỉnh (Peak Demand) thường xuất hiện vào giữa buổi sáng (09:30 - 11:30) khi hệ thống điều hòa HVAC phải bù trừ bức xạ mặt trời cực đại kết hợp phụ tải máy tính và con người.
- Việc vượt công suất đỉnh không chỉ làm tăng tiền điện theo khung giờ cao điểm (gần 5.000 VNĐ/kWh) mà còn có nguy cơ bị EVN phạt công suất phản kháng và tăng chi phí công suất đặt (Demand Charge).

## 2. Các biện pháp kỹ thuật dịch chuyển phụ tải
- **Làm mát tích trữ trước (Pre-cooling)**:
  - Tận dụng khung giờ thấp điểm (04:00 - 07:00 sáng, giá điện ~1.700 VNĐ/kWh) để làm lạnh sâu không gian tòa nhà xuống $23^\circ\text{C}$.
  - Khi bước vào giờ cao điểm (09:30), nâng nhiệt độ đặt lên $25.5^\circ\text{C} - 26^\circ\text{C}$ để giảm tải cho chiller từ $20\% - 30\%$.
- **Tắt luân phiên thiết bị phụ trợ (Staggered Scheduling)**:
  - Không khởi động đồng thời nhiều thiết bị có công suất lớn (máy bơm nước sinh hoạt, thang máy chở hàng, thiết bị bếp căn tin) trong khung giờ 09:30 - 11:30.
  - Bơm nước cấp lên bể mái vào ban đêm từ 22:00 - 04:00 sáng.
- **Tự động sa thải phụ tải không ưu tiên (Load Shedding)**:
  - Hệ thống BEMS tự động giảm $30\%$ công suất chiếu sáng khu vực sảnh, bãi đỗ xe và hành lang trong 2 khung giờ cao điểm.

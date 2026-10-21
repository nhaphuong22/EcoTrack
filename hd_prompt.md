Dưới đây là **Quy trình 3 bước chuẩn chỉnh** kết hợp **BMAD + Ponytail** đúng theo thói quen thao tác của bạn trong dự án TerraWatch:

---

### 🔹 BƯỚC 1: TẠO STORY SPEC (TINH GỌN TASK)
Dùng khi bạn muốn phân rã một Story từ `epics.md` thành file spec chi tiết nhưng không bị "bôi" task thừa.

👉 **Prompt bạn gửi:**
```markdown
/bmad-create-story [Copy Tên Story ở đây, ví dụ: Story 1.1: Multi-Role User Registration & Authentication (Register / Login / JWT)]
Áp dụng Ponytail:
- Giữ đúng ranh giới Microservice và Schema theo architecture.md.
- Tasks và Technical Guidance tinh gọn, tận dụng thư viện/tính năng có sẵn (PostGIS, Spring Security/jjwt, FastAPI built-in).
- Không tạo các task abstraction thừa (không generic repository, không mapper đa tầng, không interface 1 class).
```

---

### 🔹 BƯỚC 2: LẬP TRÌNH STORY (CODE GỌN, CHẠY NGAY)
Dùng khi file story (như file `1-1-multi-role-user-registration-authentication-register-login-jwt.md`) đã sẵn sàng và bạn muốn AI bắt tay vào code.

👉 **Prompt bạn gửi:**
```markdown
/bmad-dev-story
Story: [_bmad-output/implementation-artifacts/tên-file-story.md]
Chế độ: /ponytail full

Yêu cầu thực thi:
1. Tuân thủ ranh giới Microservice của service mục tiêu.
2. Áp dụng Ponytail Ladder: 
   - Tái sử dụng models, utils, configs đã có trong service trước khi viết mới.
   - Code ngắn nhất, diff nhỏ nhất, dùng Spring Data JPA / FastAPI / PostGIS query trực tiếp thay vì đẻ thêm class/layer trung gian.
   - Hoàn thành đầy đủ các checkbox Tasks và Acceptance Criteria (AC).
3. Code trước, giải thích ngắn gọn tối đa 3 dòng.
```

---

### 🔹 BƯỚC 3: CODE REVIEW (KIỂM TRA AC & QUÉT MỠ THỪA)
Dùng sau khi dev xong, trước khi commit/merge code để đảm bảo vừa đúng nghiệp vụ vừa không rác codebase.

👉 **Prompt bạn gửi:**
```markdown
/bmad-code-review
Review Story: [_bmad-output/implementation-artifacts/tên-file-story.md]
Kèm theo /ponytail-review:

1. [BMAD]: Đảm bảo code chạy đúng 100% Acceptance Criteria của Story, an toàn bảo mật và đúng ranh giới service.
2. [Ponytail]: Săn lùng over-engineering:
   - Chỉ ra các class/hàm/interface thừa có thể xóa bỏ.
   - Chỉ ra các đoạn code dài dòng có thể rút gọn thành 1 dòng (bằng stdlib hoặc built-in framework).
   - Báo cáo theo format: 1 dòng cho mỗi vị trí đề xuất cắt giảm.
```

---

### 📌 Thẻ tóm tắt nhanh (Quick Card để lưu lại):

| Bước | Lệnh chính | Nhiệm vụ của Ponytail |
| :--- | :--- | :--- |
| **1. Create Story** | `/bmad-create-story` + `[Tên Story]` | Chặn việc vẽ task cồng kềnh, tập trung đúng AC |
| **2. Dev Story** | `/bmad-dev-story` + `[Tên file]` | Viết code ít dòng nhất, tận dụng cái sẵn có, không boilerplate |
| **3. Code Review** | `/bmad-code-review` + `[Tên file]` | Bắt lỗi nghiệp vụ + chỉ ra code thừa cần xóa |

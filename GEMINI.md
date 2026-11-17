# Hướng dẫn dự án EcoTrack

## Quy tắc xử lý lệnh /bmad (BMAD + Ponytail)
Khi người dùng nhập `/bmad` hoặc yêu cầu quy trình BMAD, hãy tự động hiển thị ngay bảng mẫu prompt/comment template theo chuẩn quy trình trong `hd_prompt.md`:

```markdown
### 📋 Quy trình 3 bước BMAD + Ponytail:

1. **Tạo Story Spec:**
/bmad-create-story [Tên Story]
Áp dụng Ponytail: Giữ đúng ranh giới Microservice & Schema, tasks tinh gọn, không abstraction thừa.

2. **Lập trình Story:**
/bmad-dev-story
Story: [_bmad-output/implementation-artifacts/tên-file.md]
Chế độ: /ponytail full

3. **Code Review:**
/bmad-code-review
Review Story: [_bmad-output/implementation-artifacts/tên-file.md]
Kèm theo /ponytail-review (Lean / Bloated / Over-engineered)
```

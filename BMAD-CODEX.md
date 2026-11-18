# Dùng BMAD với Codex trong EcoTrack

BMAD đã được cài tại `_bmad/` và đăng ký cho Codex qua `.agents/skills/`.
Mở thư mục EcoTrack trong Codex. Nếu vừa cài hoặc thay đổi skill, mở một phiên mới để kiểm tra danh sách skill.

Gửi một trong các prompt sau trong chat:

| Mục đích | Prompt |
| --- | --- |
| Xác định bước tiếp theo | `$bmad-help` |
| Viết hoặc cập nhật yêu cầu | `$bmad-prd tạo PRD cho tính năng quản lý tòa nhà` |
| Thiết kế kiến trúc | `$bmad-architecture thiết kế kiến trúc cho tính năng quản lý tòa nhà` |
| Triển khai | `$bmad-build thêm API quản lý tòa nhà` |
| Review thay đổi | `$bmad-code-review review các thay đổi hiện tại` |
| Kiểm tra tiến độ | `$bmad-sprint-planning show sprint status` |

Cũng có thể yêu cầu bằng ngôn ngữ tự nhiên, ví dụ: “Dùng BMAD để triển khai tính năng cảnh báo tiêu thụ điện”.
Đây là tên skill gửi trong chat, không phải lệnh PowerShell. Với một giai đoạn BMAD mới, nên dùng phiên chat mới và chỉ rõ tài liệu đầu vào.

## Kiểm tra cấu hình

Chạy tại thư mục gốc dự án:

```powershell
uv run _bmad/scripts/resolve_config.py --project-root "C:/Users/ADMIN/Desktop/EcoTrack"
```

Resolver cần Python 3.11 trở lên. Có thể kiểm tra trực tiếp bằng Python đã cài:

```powershell
python _bmad/scripts/resolve_config.py --project-root "C:/Users/ADMIN/Desktop/EcoTrack"
```

Workflow có lệnh `uv run --no-cache ...render_skill.py` phải chạy đúng lệnh trong `SKILL.md`.
Thay đổi cấu hình dùng chung trong `_bmad/custom/config.toml`; thay đổi cá nhân trong `_bmad/custom/config.user.toml`.
Giao tiếp mặc định bằng tiếng Việt; ngôn ngữ tài liệu hiện giữ English theo bản cài.

Kết quả lập kế hoạch nằm tại `_bmad-output/planning-artifacts/`, triển khai tại `_bmad-output/implementation-artifacts/`, kiểm thử tại `_bmad-output/test-artifacts/`.

## Khi chuyển sang máy khác

`.agents/` hiện bị bỏ qua bởi Git, nên clone repository sẽ không mang theo các skill này.
Khi thiết lập máy khác, cần khôi phục hoặc cài BMAD cho Codex để có đủ `.agents/skills/` và các tài nguyên đi kèm.
Không cần cài lại trên máy hiện tại nếu các skill đã xuất hiện trong Codex.

Tài liệu chính thức về skill: https://learn.chatgpt.com/docs/build-skills

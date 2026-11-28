# Nguồn tích hợp và nguyên tắc giữ dữ liệu

Đích duy nhất: `codex/mrbean-full-integration` trong `ValerieBV/MrBean`.

| Nhánh đọc | Commit snapshot | Nội dung |
| --- | --- | --- |
| `codex/ai-dashboard-bv` | `d03eab6c0fdc9287a6652c1692a6930033e28c75` | Nền tích hợp AI/dashboard, queue, private media và quy tắc bài đọc chỉ ghi âm |
| `feature/setup-web-admin` | `a2e0c37ed8e4e2a014679f0903738a450025b76c` | Tài khoản, vai trò, thông báo, khóa/lớp, ghi danh, hạn mức và đơn miễn |
| `assignments` | `0254880f397168a31132197d074db8231a30c9ef` | Ngân hàng bài tập, câu hỏi/đáp án, từ vựng/câu luyện, tiến độ và bản nháp |
| `AI`, `master` | `eb46f033a50830d245cb38b0cb4c3c2ecdaa9dc9` | Gốc lịch sử dự án |

Commit tích hợp ghi nhận các đầu nhánh A/B làm parent bổ sung. Chỉ ref của nhánh mới được
cập nhật. Không cập nhật nội dung hoặc ref các nhánh nguồn, không tự merge PR.

Các file có cùng đường dẫn như `core/settings.py`, `templates/base.html`, `urls.py`
được hòa giải trên nhánh mới thành một ứng dụng chạy chung. Không chồng nguyên file
cấu hình của nhánh này lên nhánh khác làm mất app hoặc luồng đã có.

## Những phần giữ và hoàn chỉnh

- Model/migration nguồn A và B, quan hệ LessonProgress/QuestionResponse/SpeakingRecording vẫn tồn tại.
- Khôi phục các đường dẫn kỹ năng, mở lớp, làm bài theo lesson, autosave, submit và
  sửa/xóa câu hỏi/từ vựng; backend dùng ghi danh và phân quyền thật.
- Một mẫu HTML/CSS/JS local thay các phong cách rời rạc; menu đúng vai trò, nút quay lại,
  phân trang, trạng thái trống/lỗi, hồ sơ/mật khẩu và thông báo có đích.
- Bổ sung vòng đời khóa/lớp/ghi danh, bản sao buổi đã giao, chính sách nộp, video riêng tư,
  phiên bản mẫu chấm, liên kết đơn miễn với nhiệm vụ và báo cáo chính thức.
- Nội dung mẫu A/B được giữ bằng `seed_source_catalog` và `seed_demo`. Không chạy lại
  seed đặt mật khẩu yếu hoặc reset tài khoản sẵn có của nhánh cũ.
- Lưu dữ liệu cũ qua migration bổ sung và lệnh nhập tiến độ; không xóa/đổi số liệu lịch sử.

Danh sách SHA của các file nguồn dùng để kiểm tra xuất xứ: [source-manifest.json](source-manifest.json).
Trong nhánh tích hợp, một file có thể được sửa để nối chức năng; manifest ghi snapshot
nguồn, không phải SHA của file sau tích hợp.

Git chỉ cung cấp code và dữ liệu mẫu được commit. Database/media nằm riêng trên máy
thành viên hoặc máy chủ không thể lấy bằng cách gộp nhánh. Cần người giữ dữ liệu cung
cấp bản sao để nhập vào môi trường mới; không có tuyên bố đã sao chép DB thật.

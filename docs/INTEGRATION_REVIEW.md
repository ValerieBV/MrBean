# Đối chiếu tích hợp giao diện và quy trình — 27/10/2026

Nhánh thay đổi duy nhất: `codex/mrbean-full-integration`. Nhánh nguồn chỉ đọc;
không cập nhật hay gộp ngược. Mốc đối chiếu lưu trong
`branch-integration-2026-10-27.json`.

## Giao diện nguồn

| Nguồn | Phần sử dụng |
| --- | --- |
| `feature/setup-web-admin` | Tài khoản, lớp học, ghi danh, phân công giáo viên, đơn miễn và shell quản trị đã nhập trước đó; giữ bố cục. |
| `assignments` tại `9a52078` | Toàn bộ 15 template mới: ngân hàng/kỹ năng/buổi/hộp thoại; lớp/kỹ năng/bài làm học viên; shell quản lý, shell học viên, đăng nhập và Django Admin. |
| `codex/ai-dashboard-bv` | Worker, dự phòng chấm thủ công, báo cáo và phân quyền đã tích hợp; giữ điểm cuối cùng và bỏ SLA theo yêu cầu. |
| `AI`, `master` | Cùng commit, khung dự án chung; không có template chức năng bổ sung. |

Tài khoản/lớp giữ Be Vietnam Pro và Bootstrap của nguồn A. Bài tập giữ
Roboto/Montserrat, bố cục thẻ/bảng/hộp thoại và thanh kỹ năng của nguồn B. Menu
được nối sang các phân hệ theo vai trò. Font, Tailwind CSS và Font Awesome được
đóng gói trong static, có giấy phép, không cần CDN hoặc cài Node khi chạy ứng dụng.

Các adapter giữ yêu cầu đã chốt: dùng ghi danh thật thay lớp mẫu; Listening mới
là trắc nghiệm theo snapshot; Speaking ghi âm, chuyển transcript, không chấm
phát âm; Vocabulary nộp văn bản/ảnh để đếm lượt, không chỉ bấm tự hoàn thành.
Bài đã giao khóa nội dung; có sao chép và cập nhật mẫu theo lớp. Báo cáo chỉ
công bố điểm cuối cùng. Hỏi AI vẫn mở từ kết quả của chính bài đã chấm.

## Kiểm tra quy trình

| Chặng | Hành vi được kiểm tra |
| --- | --- |
| Đăng nhập | Cùng xác thực thật cho hai giao diện; học viên vào chọn lớp; staff vào tổng quan; chỉ chấp nhận `next` an toàn. |
| Tài khoản/lớp | Tạo khóa/lớp/tài khoản, phân công, ghi danh, hạn chế vai trò quản lý, chuyển/ngừng lớp giữ lịch sử. |
| Ngân hàng/giao bài | Ba kỹ năng, buổi/nội dung, hộp thoại tạo/sửa/xóa qua POST, khóa bài đã giao, lớp phụ trách, hạn nộp/thứ tự và snapshot. |
| Học viên | Chọn lớp thật, tiến độ và danh sách theo kỹ năng; không lộ bài chưa giao/chưa mở hoặc lớp khác. |
| Listening | Lưu/khôi phục nháp, chọn đáp án, nộp và chấm theo đáp án sẵn có. |
| Speaking | Video/lời mẫu, micro, nghe lại/nộp; AI lỗi vào hàng thủ công; giáo viên kiểm tra và xác nhận điểm. |
| Vocabulary | Thẻ từ/nghĩa/ví dụ theo snapshot; gửi văn bản/ảnh; đếm số lượng và dự phòng khi ảnh/AI lỗi. |
| Miễn bài | Đúng bài/hạn mức; không miễn Listening; duyệt/từ chối/hủy, không trừ lặp. |
| Báo cáo | Điểm cuối cùng, nộp lại, thống kê và CSV theo quyền; quản lý không chấm thay giáo viên. |
| Hỗ trợ | Hỏi AI từ kết quả, chuyển lịch sử cho giáo viên; liên hệ quản lý riêng, thông báo/phản hồi. |
| Truy cập | Quyền ở backend/API/media, CSRF/POST, chống gửi trùng và truy cập chéo. |

Kiểm thử Django bao gồm cả nâng cấp database cũ và các đường lỗi. Trình duyệt
kiểm tra luồng chính, hộp thoại, ba vai trò, màn hình nhỏ và các trang nhập từ
nguồn. Tương phản cao kiểm tra riêng; màu mặc định giữ nguồn. OpenAI được giả
lập trong kiểm thử, chưa dùng key thật để xác nhận chất lượng trả lời thực tế.

## Cập nhật và vận hành

Kích hoạt môi trường ảo rồi chạy:

```bash
git switch codex/mrbean-full-integration
git pull origin codex/mrbean-full-integration
python manage.py migrate
python manage.py collectstatic --noinput
```

Khởi động lại web server. Lần tích hợp giao diện này không thêm model/migration
hay thư viện Python. Migrate vẫn cần nếu database thiếu bảng hỗ trợ của phiên
bản trước; không xóa database/media. Cấu hình `OPENAI_API_KEY`, worker và watchdog
theo README_AI. Static đã biên dịch; nếu sửa class về sau, dùng Tailwind 3.4.17.

Học viên: `/hoc-tap/` → lớp → `/hoc-tap/ky-nang/` → kỹ năng → bài đã giao → kết quả
→ hỏi AI/giáo viên. Giáo viên: ngân hàng → kỹ năng → buổi/nội dung → giao lớp →
bài đã giao/hàng chờ → xác nhận kết quả. Báo cáo/liên hệ/quản lý lớp qua menu.

Kết quả kiểm tra: 182 kiểm thử Django đạt; system check và migration drift không có lỗi. Kiểm tra trình duyệt gồm đăng nhập theo vai trò, ba kỹ năng, tạo/sửa/xóa bằng hộp thoại, miễn bài, báo cáo/CSV và hỏi đáp/liên hệ.

Trình duyệt: 38 trang kiểm tra tiếp cận không có vi phạm ở chế độ tương phản cao; không lỗi JavaScript/HTTP. Các màn hình nguồn kiểm tra ở 1440/768/390px.

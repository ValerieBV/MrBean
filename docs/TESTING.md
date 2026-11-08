# Kiểm tra nhánh tích hợp

## Backend và dữ liệu

Từ thư mục có `manage.py`, kích hoạt virtualenv:

```sh
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
python manage.py collectstatic --noinput
```

Các kiểm thử dùng database test và media tạm. Không dùng API key thật, không gọi API có phí.

Phạm vi kiểm tra:

- Quyền admin/quản lý/giáo viên/học viên cho trang, JSON API và audio/video/ảnh.
- Tạo khóa/lớp/tài khoản, ghi danh, chuyển giáo viên/lớp, kết thúc lớp và giữ lịch sử.
- Ngân hàng bài tập, đáp án nghe, bản sao buổi đã giao, khóa sửa/xóa nội dung có lịch sử.
- Giao bài: buổi rỗng, lỗi đúng bài/câu, dạng 2 chỉ A/B/C, file bị thiếu, thời hạn sai,
  lớp thiếu giáo viên, giao trùng, quyền lớp và danh sách học viên hoạt động.
- Chấm nghe theo key, câu bỏ trống, chống câu hỏi lạ và chống tạo trùng lần nộp.
- Chỉ nhận ghi âm cho bài đọc, ASR transcript, so lời mẫu, phiên bản mẫu và snapshot cũ.
- Từ vựng đủ/thiếu lượt, không dùng lượt thừa bù từ thiếu, ảnh lỗi/trùng chuyển thủ công.
- Claim queue, timeout/deadline, watchdog và kết quả trả muộn; API lỗi không làm mất bài.
- Giáo viên xác nhận một lần, quản lý không được chấm, điểm cũ giữ khi nộp lại đang chờ.
- Đơn miễn gắn đúng nhiệm vụ, hạn mức một lần, hủy đơn, chống duyệt sai lớp và miễn nghe.
- Lưu nháp và hết hạn 24 giờ; bài khóa/chưa mở/đóng/quá hạn/ngừng ghi danh.
- Dashboard có cả người chưa nộp, loại bài miễn, cảnh báo hỗ trợ đúng phạm vi, CSV có cùng quyền.
- Nâng cấp từ schema nguồn: ID, điểm, transcript, đề chấm và quota cũ không đổi. Nếu có hai
  ghi danh active, dừng với hướng dẫn xử lý thay vì tự xóa dữ liệu.
- Dữ liệu nullable từ nguồn, lớp chưa có giáo viên, người biên soạn cũ, đơn bị hủy và Django Admin.

## Kiểm thử bằng trình duyệt

Cần Node.js 22.12 trở lên, ffmpeg có trên PATH và virtualenv Python đã cài dependencies.
Từ thư mục repository:

```sh
cd tests/browser
npm ci
npx playwright install chromium
npm test
```

Trên Linux có thể cần `npx playwright install --with-deps chromium`. Nếu Python chạy từ
môi trường khác, đặt `MRBEAN_PYTHON` thành đường dẫn Python đó. Có thể dùng Chromium đã
cài bằng `MRBEAN_CHROMIUM_PATH`.

Bộ kiểm tra tự tạo **database và media tạm riêng**, seed tài khoản demo, tắt API key,
chạy web tại `127.0.0.1:8765` rồi thực hiện:

1. Admin tạo khóa, lớp, tài khoản, ghi danh.
2. Giáo viên đi từ ngân hàng đến danh sách buổi, tạo buổi qua modal, mở nút Quản lý
   bài tập và bốn thẻ Thêm dạng 1–4. Mỗi thẻ chọn sẵn đúng dạng/số câu; tải audio/PDF,
   dán đáp án và nhập CSV. Kiểm tra giao diện soạn bài cả admin/giáo viên tại 390/768/1440 px,
   font Roboto/Montserrat, màu nền chung và nút sao chép buổi đã giao.
3. Biểu mẫu giao bài chặn buổi rỗng, liên kết sửa nội dung, xem đủ bốn bài/100 câu,
   ẩn lượt viết từ vựng với bài nghe và liên kết lượt giao cũ khi chọn trùng.
4. Học viên xem PDF trực tiếp, chọn đáp án/ghi câu trả lời ngắn, khôi phục nháp. Nộp
   thiếu câu trả lời dù được 10 điểm vẫn chưa hoàn thành; nộp đủ nhưng sai một câu
   được 9,9 điểm vẫn hoàn thành.
5. Học viên xin miễn từ vựng; giáo viên chấp thuận; mẫu số báo cáo thay đổi đúng.
6. Giáo viên tải video kiểm thử, nhập lời mẫu, giao bài; học viên dùng micro giả lập của
   Chromium để ghi âm, nghe lại, nộp. Đây là fixture kỹ thuật, không phải bài nói đã xác minh.
7. Worker không có key chuyển bài thủ công; giáo viên chấm 7,5; học viên thấy kết quả.
8. Kiểm tra menu cả ba vai trò, quản lý chỉ xem kết quả, màn hình 1440/768/390 px,
   không tràn ngang trang, không lỗi JavaScript/HTTP trên các trang sử dụng.
9. Axe kiểm tra các trang theo các quy tắc WCAG A/AA hỗ trợ. Kiểm tra tự động không thay thế
   toàn bộ đánh giá khả năng truy cập bằng người dùng thực.

Thư mục kết quả được in cuối lệnh, gồm ảnh chụp và `browser-qa-results.json`.
Đặt `MRBEAN_QA_OUTPUT` nếu muốn chọn nơi lưu kết quả. Không trỏ biến database test vào
DB thật. Bộ test không đặt lại mật khẩu hoặc sửa dữ liệu của một DB đang có.

GitHub Actions chạy Django và luồng trình duyệt riêng, lưu artifact `browser-review`.
File cấu hình: `.github/workflows/ai-dashboard.yml`.

## Kiểm tra cuối với dữ liệu thật

Do không có key hoặc media sản xuất trong repository, cần người vận hành thử một bài
đọc và một bộ ảnh từ vựng thật sau khi cấu hình API. Kiểm tra chất lượng transcript/đếm
ảnh, quyền model trong dự án API, micro trên HTTPS và việc giáo viên nhận xét/xác nhận.
`check_openai --live` chỉ thử yêu cầu văn bản nhỏ, không đủ để xác nhận toàn bộ luồng AI.

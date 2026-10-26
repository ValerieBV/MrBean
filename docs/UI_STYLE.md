# Quy chuẩn giao diện

Giao diện trong `codex/mrbean-full-integration` lấy trực tiếp từ
`feature/setup-web-admin` tại commit `a2e0c37ed8e4e2a014679f0903738a450025b76c`.
Các thay đổi được thực hiện trên nhánh tích hợp, không cập nhật nhánh mẫu.

## Nguồn giao diện

Toàn bộ 14 template của accounts/courses cùng khung `templates/base.html` được
chép từ nhánh mẫu, thay cho các template rút gọn trước đây. Danh sách file và SHA
gốc được ghi trong `UI_SOURCE_MANIFEST.json`.

Khối CSS nội tuyến trong base gốc được giữ nguyên nội dung ở
`core/static/core/reference.css`. Bootstrap 5.3.3, Bootstrap Icons 1.11.3 và các
file font được lưu cùng dự án, dùng đúng grid, typography, card, bảng, input,
dropdown và alert của nguồn. Không phụ thuộc CDN khi mở trang.

`core/static/core/app.css` chỉ áp dụng adapter cho trang mở rộng bên trong
`.integration-content`; các quy tắc này không ghi đè trang nhập từ nhánh mẫu.
Các biểu mẫu chung mở rộng cũng dùng hàng/cột, card và widget Bootstrap như mẫu.

| Thành phần | Quy định |
| --- | --- |
| Font chung | Be Vietnam Pro, dùng cho nội dung, tiêu đề, bảng, nút và trường nhập |
| Tiêu đề trang | 1,65 rem, đậm 800, in hoa, giãn chữ 0,5 px |
| Tiêu đề mục | 1,15 rem, đậm 700, in hoa, giãn chữ 0,4 px |
| Nâu đậm | `#2A1A0E`: sidebar, thẻ thống kê, chữ chính, nút phụ |
| Kem sáng | `#FEF3E2`: nền trang, thanh đầu trang và vùng thông tin |
| Cam cháy | `#D4621A`: số liệu nổi bật, biểu tượng thương hiệu, viền nhấn |
| Vàng cam | `#F4AE52`: menu đang chọn, biểu tượng trên nền nâu, nút xuất báo cáo |
| Bố cục | Sidebar 270 px; thanh đầu trang cố định khi cuộn; nội dung cách lề 2 rem |
| Khối dữ liệu | Nền trắng, viền cam mảnh, bo góc 16 px, bảng có đầu nền kem |
| Thao tác | Nút chính bo tròn, nút sửa màu nâu, trạng thái có nhãn chữ và màu |

Mặc định giữ màu và trạng thái hover của giao diện nguồn. Chữ có dấu dùng các
độ đậm 300, 400, 500, 600, 700 và 800; không dùng độ đậm trung gian giả lập.

Font WOFF2 được lưu trong `core/static/core/fonts/`, kèm giấy phép SIL OFL 1.1.
Nguồn: https://github.com/google/fonts/tree/main/ofl/bevietnampro.
Icon trên các trang gốc dùng đúng icon font Bootstrap Icons, kèm giấy phép MIT
trong `core/static/core/vendor/`. SVG ở module mở rộng vẫn dùng cùng bộ icon.

Trên tablet/điện thoại, menu chuyển sang nút mở/đóng; bảng cuộn trong khung riêng,
thẻ thống kê xuống hàng và biểu mẫu giữ đủ nhãn/trạng thái lỗi. Menu tài khoản mở
bằng chuột hoặc bàn phím; thao tác đăng xuất tiếp tục dùng POST và CSRF.

## Các adapter cần cho quy trình tích hợp

Khung sidebar/thanh đầu trang được giữ cả trước và sau đăng nhập. Menu quản trị
đặt theo thứ tự tài khoản, lớp học, miễn BTVN, thông báo và Django Admin; các chức
năng mở rộng vẫn truy cập trong nhóm “Bài tập & báo cáo”. Footer chỉ nằm ở cuối sidebar.

Danh sách tài khoản giữ đủ bốn thẻ thống kê, bảng sáu cột và tiến trình hạn mức
của nguồn. Các số liệu, danh sách hạn mức, đơn chờ duyệt và lịch sử đơn của học
viên được cấp dữ liệu thật từ view hiện tại. Trang lớp và chi tiết lớp giữ lại
toàn bộ thẻ, banner quota, bảng học viên và bảng đơn chờ duyệt của nguồn.

Form tạo/sửa lớp, phân công giáo viên và ghi danh được nối tới đúng template gốc,
thay vì dùng form rút gọn. Form xin miễn chọn đúng bài đã giao thay cho các trường
loại bài/tiêu đề tự do của phiên bản cũ. Form xét duyệt giữ lựa chọn liên kết bài
cho đơn cũ. Thông báo và đăng xuất tiếp tục dùng POST + CSRF; form vẫn hiển thị
lỗi, giữ redirect sau đăng nhập và dữ liệu đã nhập khi có lỗi.

Các trang giữ phân trang/lọc, thao tác hủy đơn, đổi trạng thái ghi danh và lịch sử
bài tập. Quản lý chỉ theo dõi các đơn; giáo viên phụ trách/admin xét duyệt. Nút
đặt lại mật khẩu ở trang sửa tài khoản. Xóa tài khoản/ngừng ghi danh vẫn giữ lịch
sử theo quy trình hiện hành, nội dung xác nhận giải thích đúng hành vi này.

Thông báo sau đăng nhập được hiển thị trong dải riêng dưới thanh đầu trang và có
nút đóng. Module báo cáo, giao bài, ghi âm và chấm AI vẫn truy cập trong nhóm
“Bài tập & báo cáo”. Không thay đổi models, migration hay quy tắc chấm bài.

## Kiểm tra hiển thị

Đối chiếu bản gốc và bản tích hợp bằng cùng dữ liệu, cùng viewport 1536 px và cùng
font. So sánh 22 màn hình, gồm 14 template gốc và các biến thể giáo viên/học viên;
đo font, màu, padding, vị trí và chiều rộng của sidebar, brand, topbar, content và
card chính. Kiểm tra thêm 10 màn hình điện thoại 390 px, dropdown và menu bàn phím.

Một số màu chữ nhỏ của nguồn chưa đủ tương phản WCAG AA. Để giữ giao diện mặc định
đúng mẫu, bộ màu tăng tương phản chỉ bật theo thiết lập hệ điều hành
`prefers-contrast: more`; kiểm tra Axe trong workflow trình duyệt áp dụng rõ chế
độ này. Ảnh so sánh và ảnh giao diện mặc định dùng `no-preference`.

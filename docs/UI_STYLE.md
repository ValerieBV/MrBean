# Quy chuẩn giao diện

Giao diện trong `codex/mrbean-full-integration` tham chiếu trực tiếp
`feature/setup-web-admin` tại commit `a2e0c37ed8e4e2a014679f0903738a450025b76c`.
Các thay đổi được thực hiện trên nhánh tích hợp, không cập nhật nhánh mẫu.

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

Sắc cam đậm `#B74F11` đã có trong trạng thái hover của nhánh mẫu được dùng cho nút
chữ trắng và chữ cam nhỏ để giữ độ tương phản. Chữ có dấu được kiểm tra với các
độ đậm 400, 500, 600, 700 và 800; không dùng độ đậm trung gian giả lập.

Font WOFF2 được lưu trong `core/static/core/fonts/`, kèm giấy phép SIL OFL 1.1.
Nguồn: https://github.com/google/fonts/tree/main/ofl/bevietnampro.
Các SVG lấy từ Bootstrap Icons 1.11.3, kèm giấy phép MIT trong
`core/static/core/licenses/bootstrap-icons-MIT.txt`. Không cần tải font hoặc
thư viện giao diện từ CDN lúc mở trang.

Trên tablet/điện thoại, menu chuyển sang nút mở/đóng; bảng cuộn trong khung riêng,
thẻ thống kê xuống hàng và biểu mẫu giữ đủ nhãn/trạng thái lỗi. Menu tài khoản mở
bằng chuột hoặc bàn phím; thao tác đăng xuất tiếp tục dùng POST và CSRF.

## Căn lại theo ba ảnh tham chiếu

Khung sidebar/thanh đầu trang được giữ cả trước và sau đăng nhập. Menu quản trị
đặt theo thứ tự tài khoản, lớp học, miễn BTVN, thông báo và Django Admin; các chức
năng mở rộng vẫn truy cập trong nhóm “Bài tập & báo cáo”. Footer chỉ nằm ở cuối sidebar.

Đăng nhập dùng thẻ nâu ở giữa vùng nội dung, tiêu đề 1,75 rem, trường nhập có ô biểu
tượng bên trái. Trang lớp rỗng dùng biểu tượng thư mục và thông báo trên nền kem;
bộ lọc lớp nằm trong mục mở rộng. Trang miễn bài dùng các nút lọc trạng thái ngang,
bảng tám cột và ô trống có biểu tượng inbox, đồng thời giữ thao tác duyệt/hủy và phân trang.

Thông báo sau đăng nhập được hiển thị trong dải riêng dưới thanh đầu trang và có
nút đóng. Nội dung phiên đăng nhập, phân quyền, dữ liệu lớp và quy tắc chấm không đổi.

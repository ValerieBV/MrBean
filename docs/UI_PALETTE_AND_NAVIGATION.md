# Giao diện và thanh điều hướng

Áp dụng cho nhánh `codex/mrbean-full-integration` theo bảng màu được duyệt:

| Vai trò màu | Mã |
| --- | --- |
| Nền kem | `#FEF3E2` |
| Mục đang chọn, điểm nhấn vàng | `#F4AE52` |
| Viền, biểu tượng và điểm nhấn cam | `#D4621A` |
| Thanh bên, chữ và nút phụ màu nâu | `#2A1A0E` |

Các shell quản trị, ngân hàng bài tập và học viên dùng cùng
`templates/core/sidebar.html`, `core/palette.css` và `core/navigation.js`.
Menu hiển thị trực tiếp theo vai trò, không có nhóm dropdown. Hỏi AI vẫn mở từ
trang kết quả, không thêm vào menu. Dropdown tài khoản trên thanh đầu trang vẫn
giữ chức năng hồ sơ/đăng xuất hiện có.

Trên máy tính, nút menu ở đầu trang hoặc nút X trong thanh bên đóng/mở toàn bộ
thanh bên. Trạng thái được ghi nhớ trên trình duyệt khi đổi trang hoặc tải lại.
Trên điện thoại/máy tính bảng, thanh bên mặc định đóng, mở phủ trên nội dung;
bấm X, vùng nền tối hoặc Escape để đóng. Khi mở, focus nằm trong menu; khi đóng,
focus trở lại nút mở. Nội dung nền không nhận thao tác khi menu đang phủ lên.
Menu dài có vùng cuộn riêng, giữ nút đóng và thông tin tài khoản luôn truy cập được.

Màu được đồng bộ cho đăng nhập, các trang quản lý, bài tập, kết quả, báo cáo,
liên hệ và Django Admin. Thẻ/bảng/biểu mẫu, các font nội dung và quy trình backend
được giữ lại; font thanh bên dùng Be Vietnam Pro thống nhất. Chữ nhỏ dùng nâu
trên nền sáng hoặc kem trên nền nâu để dễ đọc; màu cam dùng cho điểm nhấn.

Không có thay đổi model, migration hay thư viện. Khi cập nhật code, chạy:

```bash
python manage.py collectstatic --noinput
```

Khởi động lại web server rồi tải lại trang. Kiểm thử trình duyệt bao gồm đóng/mở
và ghi nhớ thanh bên qua các shell, phân quyền menu, phím Escape, menu không
dropdown, các kích thước 1440/768/390px và kiểm tra tương phản của giao diện.

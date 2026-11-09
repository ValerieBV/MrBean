# Nhập từ vựng hàng loạt

Vào **Ngân hàng bài tập → Vocabulary → chọn buổi → Nhập từ hàng loạt**.
Giáo viên nhập vào buổi do mình tạo; admin/quản lý nhập được các buổi còn cho sửa.

## Nhập nhanh

Dán mỗi từ hoặc cụm từ một dòng. Chỉ có từ là bắt buộc:

```text
department
issue
corporate
sign up
```

Có thể sao chép cả cột từ từ Excel. Nếu có nghĩa, sao chép hai cột **Từ, Nghĩa**.
Nếu đủ thông tin, dùng bốn cột **Từ, Loại từ, Nghĩa, Ví dụ**. Ví dụ nhập bằng dấu `|`:

```text
department | bộ phận
sign up | đăng ký
```

Hoặc tải CSV/TXT UTF-8, tối đa 1 MiB. Nút **Tải CSV mẫu** có sẵn trong trang.
CSV chấp nhận tiêu đề `word,word_type,meaning,example` hoặc `Từ,Loại từ,Nghĩa,Ví dụ`;
có thể thêm cột STT. Nội dung có dấu phẩy phải đặt trong dấu nháy kép như CSV thông thường.
Tệp Excel `.xlsx` cần lưu thành CSV UTF-8 hoặc sao chép các ô vào ô dán danh sách.

## Kiểm tra và giao bài

1. Chọn một cách nhập: dán danh sách hoặc tải tệp. Mỗi lần tối đa 500 từ.
2. Bấm **Xem trước danh sách**. Chưa có từ nào được lưu ở bước này.
3. Kiểm tra từ, nghĩa, loại từ, ví dụ và các dòng trùng. Từ trùng được bỏ qua,
   không ghi đè thông tin đang có; không phân biệt chữ hoa/thường khi kiểm tra trùng.
4. Bấm **Thêm … từ vào buổi**. Các từ mới nối tiếp thứ tự đang có.
5. Về buổi học, chọn **Giao cho lớp**, chọn lớp, số lượt viết mỗi từ và hạn nộp.

Buổi đã giao hoặc đã có tiến độ học viên được giữ nguyên. Dùng **Sao chép** để
tạo buổi mới rồi nhập bổ sung. Xem trước có hiệu lực 30 phút; hết hạn thì xem trước lại.

## Cập nhật dự án

Sau khi cập nhật đúng nhánh `codex/mrbean-full-integration`, chạy:

```sh
python manage.py migrate
```

Migration `0008_optional_vocabulary_meaning` cho phép để trống nghĩa ở cả nhập từng từ
và nhập hàng loạt. Không thay đổi nội dung các từ đã có và không cần cài thêm thư viện.

# Đáp án, lời giải và hỏi AI cho bài nghe

## Cập nhật hệ thống

```bash
python manage.py migrate
python manage.py collectstatic --noinput
```

Khởi động lại web server sau khi cập nhật nhánh `codex/mrbean-full-integration`.
Không cần cài thư viện mới. Migration `assignments.0009` thêm lời giải của bài nghe;
`support.0002` giữ các cuộc trao đổi hiện có và thêm hội thoại riêng cho từng câu.

## Nhập Word

Vào **Ngân hàng bài tập → Listening → Quản lý bài tập → Thêm dạng**.
Trong **Đáp án và giải thích**, bấm **Tải mẫu Word**, điền nội dung rồi tải lại file
`.docx`. Hệ thống tự đọc, điền bảng đáp án và mở phần kiểm tra có thể sửa trực tiếp.
Đối với dạng 3/4, câu hỏi và lựa chọn trong Word cũng trở thành đề học viên làm.
Đáp án đúng, giải thích, bản dịch và đoạn nghe chung chỉ xuất hiện sau khi nộp.

| Dạng | Phạm vi câu | Nội dung trong Word |
| --- | --- | --- |
| 1 | 1–6 | Đáp án và giải thích từng câu; có thể thêm lời đọc/lựa chọn |
| 2 | 7–31 | Câu hỏi nghe, ba câu đáp A/B/C, đáp án và giải thích |
| 3 | 32–70 | 13 hội thoại; mỗi hội thoại dùng chung đúng ba câu hỏi |
| 4 | 71–100 | 10 đoạn nói; mỗi đoạn dùng chung đúng ba câu hỏi |

Mỗi câu có số câu, các lựa chọn `(A)`…`(D)` hoặc `(C)`, **Đáp án:** và
**Giải thích:**. Dạng 3/4 có thêm tiêu đề **Đoạn 32–34** hoặc **Đoạn 71–73**,
**Nội dung:** và **Bản dịch:** trước ba câu của đoạn đó. Bản dịch không bắt buộc.
Mỗi câu vẫn có giải thích riêng. Có thể đặt nội dung trong đoạn văn hoặc ô bảng;
không cần tách ba câu thành ba trang.

File có thể chứa riêng một dạng hoặc cả bốn dạng với tiêu đề **PART 1**…**PART 4**
(hoặc **DẠNG 1**…**DẠNG 4**). Khi tải file, hệ thống lấy đúng dạng đang chọn.
Một bộ đánh số cục bộ 1…N sẽ được đổi đồng thời cả số câu và phạm vi đoạn.

Mỗi lần nhập phải có đủ số câu của dạng, không trùng số, đủ đáp án và giải thích.
Dạng 3/4 phải đủ đoạn và mỗi đoạn phải khớp đúng nhóm ba câu. Nội dung thiếu hoặc
đáp án mâu thuẫn sẽ bị từ chối; hệ thống không tự đoán. File tối đa 10 MiB, có văn
bản thực, không phải ảnh chụp chèn vào Word. Nhập Word không gọi OpenAI.

Cách dán bảng đáp án và nhập CSV/TXT vẫn có trong **Bảng đáp án · nhập trực tiếp /
CSV**. Để bổ sung lời giải cho bài đã có, mở **Thêm đáp án và giải thích** hoặc
**Xem / sửa lời giải** tại chi tiết buổi. Với bài đã giao, đáp án, câu hỏi và lựa
chọn phải khớp đề hiện có; thao tác này không chấm lại hoặc sửa bài làm học viên.

## Học viên xem lời giải

Sau khi nộp, mở **Kết quả bài tập → Đáp án và giải thích**. Chọn bài rồi chọn câu
hoặc nhóm câu. Dạng 3/4 hiển thị một đoạn chung cùng cả ba câu, mỗi câu có lựa chọn
của học viên, đáp án đúng và giải thích riêng. Dạng 2 hiện cả câu hỏi nghe và nội
dung ba câu đáp. Có thể nghe lại audio và mở bản dịch khi cần.

Lượt giao mới giữ bản chụp lời giải cùng đề đã giao. Nếu lượt giao cũ chưa có lời
giải, hệ thống chỉ dùng lời giải được bổ sung khi mã câu, số câu, file nghe, đáp án
và nội dung đề vẫn khớp. Không hiển thị lời giải của một đề khác. Bài cũ chưa được
bổ sung hiện trạng thái chưa có lời giải, không tự tạo giải thích thay giáo viên.

## Hỏi AI tại từng câu

Bấm **Hỏi AI** dưới câu chưa hiểu, nhập câu hỏi rồi gửi. Mỗi câu trong mỗi lần nộp
có lịch sử riêng; mở lại cùng câu sẽ tiếp tục cuộc trao đổi. Có thể quay lại đúng
nhóm lời giải từ trang hỏi đáp.

AI nhận câu đang hỏi, lựa chọn học viên, đáp án và lời giải chính thức. Dạng 3/4
kèm đoạn nghe dùng chung và ba câu liên quan. AI không nhận đề chưa nộp, bài của
học viên khác hoặc toàn bộ ngân hàng bài tập. Nếu thiếu căn cứ, AI phải đề nghị
hỏi giáo viên; không tự nhận đã nghe audio hay đổi kết quả.

Dùng `OPENAI_API_KEY` và `OPENAI_TUTOR_MODEL` hiện có. Không cần kết nối Colab.
Không có lời gọi API khi chỉ mở lời giải hay mở biểu mẫu hỏi AI. Nếu API lỗi, câu
hỏi được giữ lại để thử lại hoặc chuyển cho giáo viên theo luồng hỗ trợ hiện có.

## Kiểm tra

```bash
python manage.py test assignments.test_listening_solutions support
cd tests/browser
node listening_solutions.cjs
```

Kiểm tra trình duyệt dùng database/media tạm và không gọi API trả phí. Bao phủ
nhập Word, sửa bản xem trước, giấu lời giải trước nộp, nhóm ba câu, ngữ cảnh AI,
quay lại lời giải, bốn chiều rộng màn hình và kiểm tra accessibility bằng axe.

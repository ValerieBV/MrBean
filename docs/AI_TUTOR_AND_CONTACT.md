# Hỏi đáp kiến thức và liên hệ trực tiếp

## Học viên

Sau khi bài đã có kết quả, mở trang kết quả và chọn **Hỏi AI về kiến thức bài này**.
Hỏi đáp không có mục riêng trên thanh bên. Muốn mở lại cuộc trao đổi, quay lại
kết quả của đúng bài tập và chọn nút hỏi AI; lịch sử đã có được giữ nguyên.
AI giải thích từ vựng, ngữ pháp, cách hiểu nội dung đọc/nghe dựa trên bài đã chấm
và nhận xét giáo viên. Mỗi lần nộp có một cuộc hỏi đáp riêng; vào lại sẽ giữ lịch sử.
Điểm công bố không thay đổi vì cuộc hỏi đáp.

Nếu chưa hiểu hoặc cần kiểm tra cụ thể bản ghi/ảnh, chọn **Hỏi giáo viên**. Có thể
ghi thêm nội dung muốn làm rõ. Khi gửi, giáo viên phụ trách nhận thông báo và xem
câu hỏi cùng lịch sử AI. Các tin nhắn tiếp theo gửi trực tiếp cho giáo viên;
AI không tự tiếp tục trả lời sau khi đã chuyển người phụ trách.

Mục **Liên hệ & phản ánh** dành cho thắc mắc kết quả, lỗi kỹ thuật, lịch học hoặc
các phản ánh khác. Chọn giáo viên phụ trách lớp hoặc quản lý, nhập nội dung và
kết quả liên quan nếu cần. Tin liên hệ không được gửi tới OpenAI. Nếu chọn giáo
viên, kết quả đính kèm phải thuộc đúng lớp của giáo viên đó.

Học viên xem phản hồi trong cuộc trao đổi hoặc từ thông báo hệ thống. Có thể
đánh dấu đã giải đáp, rồi mở lại khi cần trao đổi thêm. Hỏi đáp đã chuyển giáo
viên vẫn giữ tuyến giáo viên khi mở lại. Nếu chưa có giáo viên hoạt động, hệ thống
hướng dẫn liên hệ quản lý thay vì gửi cho một giáo viên không phụ trách.

## Giáo viên, quản lý và admin

- Giáo viên mở **Liên hệ & phản ánh**, chọn **Câu hỏi từ bài tập** để xem câu học
  viên đã chuyển cho mình; nhập phản hồi trong cuộc trao đổi. Nội dung AI có nhãn
  riêng, không phải lời giáo viên.
- **Liên hệ & phản ánh** hiển thị tin được gửi trực tiếp tới người đang đăng nhập.
  Quản lý không đọc các cuộc AI riêng tư hoặc liên hệ gửi giáo viên khác.
- Admin được hỗ trợ các cuộc đã chuyển người phụ trách và liên hệ trực tiếp.
  Các cuộc AI chưa được học viên chuyển vẫn riêng tư, kể cả trong Django Admin.
- Người nhận phản hồi được thông báo nội bộ, kèm liên kết đúng cuộc trao đổi.
- Khi lớp đổi giáo viên, các cuộc gửi “giáo viên phụ trách lớp” được chuyển theo
  giáo viên mới; giáo viên cũ không còn quyền xem cuộc trao đổi đó.

## Cấu hình OpenAI

Dùng `OPENAI_API_KEY` hiện tại. `OPENAI_TUTOR_MODEL` mặc định bằng
`OPENAI_TEXT_MODEL` (`gpt-6-luna`); không cần key khác hoặc worker mới cho hỏi đáp.
Gọi API trong yêu cầu gửi câu hỏi, có thời gian chờ 20 giây, không tự retry.
Model cần hỗ trợ Responses API, Structured Outputs và reasoning effort `low`.

Prompt nằm trong `support/ai.py`, biến `TUTOR_PROMPT`. Model nhận ngữ cảnh bài
đã công bố của đúng học viên và tối đa 12 tin hỏi/đáp gần nhất. Lịch sử đầy đủ
vẫn lưu trong database và có phân trang trên giao diện.

Ngữ cảnh AI chỉ chứa mức hoàn thành/nhận xét giáo viên; không chứa điểm số,
nhận xét nội bộ, dữ liệu học viên khác hoặc ngân hàng câu hỏi. Với bài nghe, chỉ
lần đã có kết quả mới được dùng đề/đáp án snapshot để giải thích. Ảnh và ghi âm
không được gửi lại cho AI hỏi đáp; AI không được tự nhận đã nghe/xem chúng.

Kết quả AI dùng JSON schema gồm `answer`, `route` (`knowledge`, `teacher`, `contact`).
Đây chỉ là lời giải thích/định hướng; AI không có công cụ sửa kết quả hoặc gửi liên
hệ. Chuyển giáo viên và gửi phản ánh luôn do học viên bấm xác nhận thao tác.
Tin nhắn được hiển thị như văn bản, không thực thi HTML do người dùng/AI trả về.

Nếu thiếu key, API lỗi hoặc phản hồi không hợp lệ, câu hỏi được giữ lại và giao
diện cho thử lại hoặc hỏi giáo viên. Mỗi câu tối đa 3 lượt, mỗi học viên mặc định
30 lượt AI/ngày (`AI_TUTOR_DAILY_LIMIT` trong settings). Request bị gián đoạn có
thể thử lại sau timeout + 15 giây; kết quả trả muộn không ghi đè cuộc đã chuyển
giáo viên/đã đóng. Chống gửi trùng bằng UUID và ràng buộc một yêu cầu đang chạy
trong mỗi cuộc trao đổi.

## Cập nhật máy đang chạy

Trên nhánh `codex/mrbean-full-integration`, cập nhật code, kích hoạt virtualenv rồi chạy:

```bash
python manage.py migrate
python manage.py collectstatic --noinput
```

Khởi động lại web server. Các worker chấm bài/watchdog hiện tại tiếp tục dùng như
cũ. Không cần thêm thư viện ngoài requirements hiện có. Migration `support.0001`
chỉ thêm ba bảng cuộc trao đổi, tin nhắn và lượt hỏi AI; không sửa dữ liệu điểm cũ.
`.env` được bỏ qua trong Git; không đưa key vào mã nguồn hoặc nội dung hỏi đáp.

Nếu database của phiên bản cũ chưa có `support_conversation` (hoặc các bảng hỗ trợ
khác), mở mục liên hệ trước khi migrate có thể gây lỗi thiếu bảng. Chạy
`python manage.py migrate` trong đúng môi trường và database đang dùng, rồi tải
lại trang. Không xóa database và không cần chạy makemigrations. Phiên bản hiện
tại hiển thị thông báo tạm ngừng phù hợp với từng vai trò thay cho trang lỗi;
trang tự hoạt động ở yêu cầu tiếp theo sau migration, không tự thay đổi schema
khi người dùng truy cập. Người học không thấy lệnh hay thông tin database.

## Kiểm thử

```bash
python manage.py test support
```

Các kiểm thử dùng OpenAI giả lập, bao phủ ngữ cảnh theo quyền, kết quả đã công bố,
hội thoại nhiều lượt, API lỗi, hạn mức, gửi trùng, retry, kết quả trả muộn,
chuyển giáo viên, liên hệ riêng, thông báo, đổi giáo viên, đóng/mở lại và CSRF/XSS.
Kiểm tra trình duyệt toàn dự án cũng chạy luồng AI lỗi → hỏi giáo viên → phản hồi,
liên hệ quản lý và kiểm tra các màn hình mới. Chạy thử với key thật bằng một bài
đã có kết quả để đánh giá chất lượng câu trả lời; phép thử API có thể phát sinh phí.

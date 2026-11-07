# Quy trình và quyền sử dụng Mr Bean

## Phân quyền

| Chức năng | Admin | Quản lý | Giáo viên | Học viên |
| --- | --- | --- | --- | --- |
| Tạo khóa/lớp, phân công giáo viên, ghi danh | Toàn hệ thống | Toàn hệ thống | Xem lớp phụ trách | Xem lớp đang học |
| Tạo tài khoản | Mọi vai trò | Chỉ học viên | Không | Không |
| Đổi vai trò, đặt lại mật khẩu, vô hiệu hóa | Có, kèm kiểm tra lịch sử | Không | Không | Không |
| Sửa hồ sơ, đổi mật khẩu cá nhân | Có | Có | Có | Có |
| Đọc ngân hàng bài tập | Có | Có | Có | Chỉ nội dung đã giao |
| Sửa/xóa nội dung chưa giao | Có | Có | Buổi do mình tạo | Không |
| Sao chép buổi để tạo phiên bản mới | Có | Có | Có | Không |
| Giao bài/cập nhật hạn, quy định/video mẫu | Mọi lớp | Mọi lớp | Lớp phụ trách | Không |
| Nộp bài/lưu nháp | Không | Không | Không | Bài của chính mình, đủ điều kiện |
| Xem bài làm/điểm | Mọi lớp | Mọi lớp | Lớp phụ trách | Bài của chính mình |
| Xác nhận điểm AI/chấm thủ công | Có | Theo dõi | Lớp phụ trách | Không |
| Xin/hủy đơn miễn chờ duyệt | Không | Không | Không | Bài Speaking/Vocabulary chưa nộp của mình |
| Duyệt đơn miễn | Có | Theo dõi | Lớp phụ trách | Không |
| Báo cáo, xuất CSV | Mọi lớp | Mọi lớp | Lớp phụ trách | Dữ liệu của mình |

Quyền được kiểm tra trong backend cho trang, API và file media, không chỉ ẩn menu.
Quản lý được giữ là vai trò riêng từ phần A; admin có cả giao diện quản lý thường dùng
và tài khoản superuser tùy người vận hành cấp.

## 1. Thiết lập một lớp

Admin/quản lý mở **Danh mục khóa học → Tạo khóa học**. Sau đó vào **Quản lý lớp học →
Tạo lớp**, chọn khóa, giáo viên đang hoạt động và ngày khai giảng/kết thúc. Ngày kết thúc
không được trước ngày khai giảng. Có thể tạo lớp chưa phân công, nhưng phải phân công
một giáo viên trước khi giao bài.

Vào **Quản lý tài khoản → Tạo tài khoản**, nhập người dùng, mật khẩu và mã học viên.
Quản lý chỉ tạo được học viên. Vào chi tiết lớp → **Thêm học viên**, chọn tài khoản chưa
ở lớp active khác. Mỗi học viên có tối đa một ghi danh active; database cũng kiểm tra
quy tắc này. Hạn mức miễn được tạo từ mã học viên: T/V 8, B 5, mặc định 8.

Học viên vào muộn được đồng bộ các lượt giao đang mở, chưa hết hạn. Bài chưa giao
không được tự mở từ ngân hàng; biết mã lớp cũng không tự ghi danh được.

Chuyển lớp: cập nhật ghi danh cũ sang hoàn thành/nghỉ rồi thêm vào lớp mới. Giữ lại
bài làm và điểm cũ. Đổi giáo viên: phân công giáo viên thay thế trong chi tiết lớp;
quyền xem/chấm chuyển theo giáo viên hiện tại, người đã chấm trước đó vẫn được ghi lại.

## 2. Biên soạn và giao bài

Giáo viên mở **Ngân hàng bài tập → kỹ năng → Tạo buổi tập**, chọn chương trình và thứ tự.
Mỗi kỹ năng/chương trình/thứ tự là duy nhất.

- **Listening:** lưu buổi rồi tự thêm 1–4 bài. Bốn dạng có 6/25/39/30 câu; dạng 2
  chọn A–C, các dạng còn lại A–D. Tải audio cho từng bài, PDF bắt buộc với dạng 1
  và hiển thị trực tiếp trên web. Dán cả cột đáp án hoặc nhập CSV/TXT để tạo câu hỏi
  cùng lúc. Xem [hướng dẫn biên soạn và chấm hoàn thành](LISTENING_AND_COMPLETION.md).
- **Đọc theo video/Speaking:** tải MP4/WebM tối đa 50 MiB hoặc điền URL YouTube HTTPS;
  nhập nguyên văn đoạn cần đọc, tối đa 1.500 từ/20.000 ký tự. Các câu SpeakingTask gốc
  vẫn hiển thị để tham khảo. Không tự dùng yêu cầu nói tự do làm lời mẫu.
- **Vocabulary:** thêm từ, loại từ, nghĩa và ví dụ. Khi giao, chọn số lượt cần chép mỗi từ
  từ 1 đến 100. Không chấm chữ đẹp/xấu.

Bật buổi học, chọn **Giao cho lớp**, thời điểm mở, hạn nộp, cho phép nộp muộn và có yêu
cầu hoàn thành bài trước hay không. Backend tạo một LearningTask cho từng học viên
active, lưu yêu cầu/đáp án/số lượt viết thành snapshot. Không giao trùng cùng buổi/lớp.

Sau khi giao, buổi gốc khóa chỉnh sửa/xóa để bảo toàn dữ liệu. Dùng **Sao chép** để tạo
buổi mới có thể chỉnh sửa đầy đủ câu hỏi/từ/câu luyện. Trong **Bài tập đã giao → Chi tiết**,
giáo viên có thể đổi hạn nộp, tạm dừng nhận, bật/tắt nộp muộn và thứ tự mở bài.
Các thay đổi này không xóa bài đã nộp.

Nếu cần sửa video/lời mẫu cho một lớp, dùng **Cập nhật video & lời mẫu** ở lượt giao.
Mẫu mới chỉ áp dụng cho các lần nộp mới. Mỗi GradingJob giữ nguyên snapshot của lần đó.
Trang làm bài có mã phiên bản; nếu giáo viên đổi mẫu khi học viên đang mở trang,
lượt nộp từ trang cũ bị yêu cầu tải lại.

## 3. Học viên làm và nộp bài

Học viên đăng nhập vào **Học tập & bài tập**, chọn lớp đã ghi danh, chọn kỹ năng,
rồi chọn buổi đã được giao. Báo cáo xem riêng qua **Báo cáo học tập**.
Bài chỉ xuất hiện khi đến thời điểm giao. Nếu bật mở theo thứ tự, các bài trước cùng
kỹ năng/chương trình/lớp phải được xác nhận **hoàn thành** hoặc được miễn. Chỉ nộp bài
chưa đủ điều kiện mở bài sau; bài còn thiếu cũng chưa được tính hoàn thành.

Listening: nghe, xem PDF và chọn đáp án kèm câu trả lời ngắn cho từng câu. Câu chọn
sai ảnh hưởng điểm; bỏ lựa chọn hoặc câu trả lời ngắn ảnh hưởng mức hoàn thành. Văn
bản từ vựng, lựa chọn nghe và câu trả lời ngắn tự lưu nháp sau thay đổi, giữ trong 24 giờ. Ảnh và ghi âm không lưu nháp; cần chọn
hoặc ghi lại sau khi đóng trang. Bản nháp không được tính là đã nộp.

Đọc theo video: xem mẫu → tạm dừng video → cho phép micro → ghi âm → dừng → nghe lại →
ghi lại nếu cần → nộp. Chỉ có micro, không có ô nhập transcript hoặc chọn file audio.
Backend vẫn từ chối transcript tự nhập, kể cả qua API. Bản ghi tối đa 20 MiB. Micro cần
HTTPS hoặc localhost và trình duyệt có MediaRecorder.

Vocabulary: nhập văn bản hoặc tải tối đa 5 ảnh PNG/JPEG/WebP, mỗi ảnh tối đa 8 MiB.
Hệ thống chuẩn hóa ảnh và từ chối trang ảnh trùng. Nếu gửi cả hai dạng, AI ưu tiên
ảnh để không đếm hai lần cùng nội dung. Ảnh mờ/không đủ chứng cứ chuyển giáo viên.

Nộp lại tạo lần nộp riêng. Mã lần nộp chống tạo bản ghi trùng khi mạng lỗi và gửi lại.
Nếu có điểm chính thức cũ mà lần mới đang chờ, dashboard vẫn giữ điểm đã xác nhận và
thể hiện lần nộp lại đang chờ. Không thay điểm chính thức bằng điểm AI.

Bài đóng, lớp kết thúc, ghi danh ngừng hoạt động, đã được miễn hoặc đơn miễn đang chờ
thì không nhận bài mới. Quá hạn vẫn nhận nếu giáo viên bật nộp muộn; lưu thời điểm thật.

## 4. Chấm điểm và công bố

Listening được backend chấm ngay theo snapshot đáp án: số câu đúng / tổng câu × 10.
AI không được sử dụng để đoán đáp án. Đủ lựa chọn và câu trả lời ngắn cho mọi câu mới
được tính hoàn thành, độc lập với số câu chọn đúng. Nội dung câu trả lời ngắn được
lưu để giáo viên xem; hệ thống kiểm tra có điền, không tự chấm ngữ nghĩa của phần này.

Bài đọc/từ vựng vào queue trong DB. Worker yêu cầu OpenAI theo deadline, nhận JSON
có schema và kiểm tra lại kiểu dữ liệu. Bài đọc được chuyển từ audio sang transcript;
backend chuẩn hóa văn bản, so thứ tự từ và tính mức khớp. AI chỉ nhận xét khác biệt
transcript; không kết luận phát âm sai, vì nhận dạng có thể sai. Từ vựng được AI đếm
lượt mỗi từ, backend giới hạn số lượt hữu ích để từ viết thừa không bù từ bị thiếu.

AI thành công → **AI đã nhận xét** và thông báo cho giáo viên. AI lỗi, thiếu key,
ảnh/transcript không chắc chắn hoặc quá 300 giây → **Chờ giáo viên**. Watchdog chạy
độc lập với worker, kiểm tra mỗi giây; kết quả AI trả muộn không ghi đè trạng thái đã xử lý.

Giáo viên mở **Tổng quan → Bài chờ chấm điểm**, nghe bản ghi/xem ảnh, đối chiếu
lời mẫu và transcript, nhập điểm 0–10 cùng nhận xét, chọn mức **Hoàn thành/Bài làm bị thiếu**,
rồi bấm **Xác nhận điểm**. Không suy ra thiếu bài chỉ từ điểm hoặc lỗi nhận dạng.
Bài cũ đã có điểm nhưng chưa có mức hoàn thành có form xác nhận riêng, giữ nguyên điểm.
Chỉ giáo viên lớp hiện tại hoặc admin được xác nhận; quản lý chỉ theo dõi.
Điểm không được xác nhận hai lần trên cùng lần nộp.

Học viên nhận thông báo nội bộ có liên kết đến kết quả. Báo cáo/dashboard và file CSV
chỉ hiển thị điểm cuối cùng; học viên xem điểm và nhận xét đã được giáo viên xác nhận.
Điểm gợi ý và nhận xét tự động được lưu nội bộ để hỗ trợ giáo viên chấm, không công bố
trong báo cáo hay API kết quả của học viên. Bài chưa được xác nhận hiển thị chờ chấm.
Bài nghe tiếp tục có điểm cuối cùng theo đáp án giáo viên đã thiết lập.
File chứng cứ được tải qua endpoint kiểm tra quyền; không mở công khai thư mục media.

## 5. Xin miễn và duyệt

Học viên mở bài chưa nộp → **Cần xin miễn bài này?** hoặc vào lớp → xin miễn. Chọn đúng
lượt giao Speaking/Vocabulary, nêu lý do. Backend lấy lớp, kỹ năng và tiêu đề từ bài;
không tin tiêu đề học viên tự nhập. Listening không được chọn hoặc duyệt miễn.

Trong khi chờ, bài tạm ngừng nhận nộp. Học viên có thể hủy đơn để làm lại. Không trừ
quota lúc gửi/hủy/từ chối. Giáo viên lớp hoặc admin duyệt, kiểm tra quota và bài chưa nộp
trong transaction; chấp thuận trừ đúng một lượt và liên kết bài được miễn. Không duyệt lại.

Đơn cũ chỉ có tiêu đề vẫn đọc được. Trước khi duyệt trên giao diện, phải chọn liên kết
với bài đã giao cùng lớp/kỹ năng để dashboard loại đúng nghĩa vụ cần nộp.

## 6. Báo cáo và kết thúc lớp

Dashboard tự tải mỗi 10 giây, có trạng thái cập nhật/lỗi, lọc lớp, kỹ năng, ngày giao,
tên bài/học viên và phạm vi đang hoạt động/cả lịch sử. Các bảng phân trang. CSV áp dụng
cùng phạm vi quyền và bộ lọc, bảo vệ giá trị có thể bị hiểu là công thức bảng tính.

Chỉ số chính là **tỷ lệ hoàn thành** = số lượt giao đã được xác nhận làm đủ / số lượt
phải làm, loại bài miễn. Tỷ lệ nộp vẫn được giữ riêng: số lượt giao đã có ít nhất một
lần nộp / số lượt phải nộp. Bản nháp và bài đang chờ chấm chưa được tính hoàn thành.
Nộp lại không tăng mẫu số/tử số. Điểm trung bình lấy điểm chính thức gần nhất của từng
lượt giao. Bảng lịch sử vẫn giữ từng lần nộp, có thể nhiều dòng cho một bài.

Cảnh báo học viên cần hỗ trợ dùng bài quá hạn chưa nộp, bài đã chấm còn thiếu và thời
gian ít hoạt động. Không quy trách nhiệm chậm tiến độ cho học viên chỉ vì đang chờ chấm.
Loại bài được miễn, bài đang khóa theo thứ tự, đơn miễn chờ duyệt, lớp đóng, học viên
nghỉ/đã ngừng tài khoản. Đây là dấu hiệu để giáo viên hỗ trợ, không phải kết luận bỏ học.
Dashboard không có phần SLA.

Admin/quản lý cập nhật lớp thành ngừng hoạt động khi kết thúc. Các ghi danh active được
chuyển hoàn thành; dừng nhận bài mới. Người học xem kết quả cũ qua **Cả lịch sử**.
Nếu mở lại lớp, cần ghi danh lại học viên phù hợp một cách rõ ràng. Vô hiệu hóa tài khoản
thay cho xóa vật lý; phải phân công giáo viên thay thế trước khi vô hiệu hóa giáo viên
còn dạy lớp active. Không tự vô hiệu hóa tài khoản đang dùng hoặc bỏ admin hoạt động cuối cùng.

# Bài nghe và tiến độ hoàn thành

Áp dụng trên nhánh `codex/mrbean-full-integration`.

## 1. Đánh giá hoàn thành

| Trạng thái | Ý nghĩa | Tính hoàn thành |
| --- | --- | --- |
| Chưa làm | Chưa có bài nộp hoặc bản nháp | Không |
| Đang làm | Đã lưu nháp, chưa nộp | Không |
| Đã nộp / chờ chấm | Đã gửi, chưa có xác nhận cuối cùng | Không |
| Chưa hoàn thành | Đã chấm và xác định còn thiếu yêu cầu | Không |
| Hoàn thành | Đã chấm và xác nhận làm đủ yêu cầu | Có |
| Đã chấm · chờ xác nhận hoàn thành | Điểm cũ có sẵn nhưng chưa xác định đủ/thiếu | Không |

Bài mới chỉ có kết luận hoàn thành/chưa hoàn thành, không tạo điểm 0–10. Số câu đúng/sai được giữ để tham khảo. Với bài nghe mới, học viên phải chọn
đáp án và ghi câu trả lời ngắn cho **tất cả các câu trong buổi**. Chọn sai vẫn có thể
hoàn thành nếu đã làm đủ; chọn đúng toàn bộ nhưng bỏ câu trả lời ngắn vẫn bị thiếu.
Nội dung câu trả lời ngắn được
lưu cho giáo viên xem; hệ thống không tự chấm đúng/sai nội dung đó bằng AI.

Với bài đọc theo video và từ vựng, AI đưa đề xuất; giáo viên/admin xác nhận mức hoàn
thành và nhận xét cuối cùng. Không suy ra thiếu bài chỉ vì nhận dạng giọng nói hoặc
chữ viết không chính xác. Không chấm phát âm hay độ đẹp của chữ.

Dashboard và trang học tập tính tiến độ theo số lượt giao đã được xác nhận hoàn thành,
loại bài được miễn khỏi số phải làm. Nộp lại không làm tăng số bài. Lần nộp mới đang
chờ giữ kết quả đã xác nhận trước đó; khi lần mới được chấm, dùng kết quả của lần mới.
Nếu bật mở bài theo thứ tự, bài trước phải hoàn thành hoặc được miễn mới mở bài sau.
Hoàn thành đúng hạn được xét theo thời điểm nộp bài đã làm đủ, không theo thời gian
giáo viên chấm. Báo cáo vẫn giữ riêng số đã nộp để phân biệt với số đã hoàn thành.

## 2. Giáo viên tạo một buổi nghe

1. Mở **Ngân hàng bài tập → Listening (Xem buổi và thêm bài)**. Với buổi đã có,
   bấm **Quản lý bài tập** hoặc **Thêm bài nghe** ngay trong hàng của buổi đó.
   Với buổi mới, bấm **Tạo buổi tập listening**, nhập thông tin rồi bấm
   **Lưu buổi và thêm bài tập** để đi thẳng đến màn hình quản lý nội dung.
2. Trong phần **Thêm bài tập theo dạng**, có bốn thẻ hiển thị tên dạng, số câu,
   các lựa chọn và tài liệu cần tải. Bấm **Thêm dạng 1 / 2 / 3 / 4** để mở đúng
   biểu mẫu đã chọn. Mỗi buổi tự thêm từ **1 đến 4 bài**; không tự tạo sẵn.
3. Biểu mẫu tự chọn dạng và số câu tương ứng. Đặt thứ tự bài 1–4 và tên riêng nếu cần.

| Dạng | Số câu cố định | Lựa chọn | Tài liệu |
| --- | --- | --- | --- |
| 1 · Mô tả tranh | 6 | A, B, C, D | File nghe và PDF đề có tranh |
| 2 · Hỏi - Đáp · Câu 7–31 | 25 | A, B, C | Chỉ file nghe |
| 3 · Cuộc hội thoại ngắn | 39 | A, B, C, D | File nghe; có thể thêm PDF |
| 4 · Bài nói ngắn · Câu 71–100 | 30 | A, B, C, D | File nghe; có thể thêm PDF |

Không bắt buộc chọn đủ bốn dạng trong một buổi. Nếu thêm cả bốn thì có tổng cộng 100
câu. Các bài được thêm riêng, mỗi bài có tài liệu và bảng đáp án riêng. Số câu tự đổi
theo dạng; backend từ chối số câu không đúng quy định.

4. Tải file nghe MP3/WAV/M4A/MP4/OGG/WebM, tối đa **50 MiB/bài**. Nên dùng MP3 để
   các trình duyệt phát thuận tiện. PDF tối đa **25 MiB**, bắt buộc với dạng 1.
   PDF cần có đủ hình/đề học viên được xem và không chứa bảng đáp án đúng.
5. Với dạng 3/4, chọn một nguồn nội dung câu hỏi:
   - **PDF có văn bản:** tải PDF; hệ thống tự đọc câu hỏi và lựa chọn.
   - **Word:** dùng mục **Hoặc đọc câu hỏi từ Word (.docx)**. Chọn file để đọc tự động,
     hoặc bấm **Đọc câu hỏi từ Word** để thử lại. Không cần đính kèm thêm PDF.
   - **PDF scan/ảnh:** chọn **Đọc bản scan bằng AI**. Đọc chữ thông thường sẽ báo rõ
     khi PDF không có văn bản đọc được; hệ thống không tự gọi API có phí.
6. Câu hỏi và lựa chọn được lấy tự động từ tài liệu, không cần nhập lại từng câu.
   Trang chính chỉ hiển thị tài liệu và bảng đáp án. Nếu cần kiểm tra hoặc sửa lỗi
   nhận dạng, bấm **Kiểm tra nội dung câu hỏi** để mở cửa sổ riêng.
   Câu AI báo chưa rõ cần kiểm tra rồi bấm
   **Đã kiểm tra câu này**; hệ thống chặn lưu dạng 3/4 nếu chỉ có ký hiệu A/B/C/D.
7. Nhập đáp án đúng hàng loạt theo mục 3, rồi bấm **Lưu bài nghe và đáp án**.
   Đáp án được nhập riêng; bộ đọc PDF không tự đoán đáp án đúng.
8. Thêm các bài còn lại theo nhu cầu. Kiểm tra file nghe, PDF và bảng đáp án tại
   chi tiết buổi, rồi bấm **Giao buổi cho lớp**. Chọn lớp, thời điểm mở, hạn nộp
   và quy định nhận bài.

### Dùng Word hoặc Google Docs cho dạng 3/4

Nếu đề đang ở Google Docs, tải xuống dưới dạng **Microsoft Word (.docx)** rồi chọn
file tại mục Word trên trang tạo bài nghe. File `.doc` cũ cần lưu lại thành `.docx`.
File Word tối đa **10 MiB**, phải có văn bản thực; chèn ảnh chụp đề vào Word không
biến ảnh thành chữ. Với đề nằm trong ảnh, xuất PDF và dùng chức năng nhận dạng scan.

Word có thể dùng đoạn văn, bảng hai cột hoặc danh sách đánh số tự động thông dụng.
Để đọc thuận tiện, mỗi câu và mỗi lựa chọn nên nằm trên một dòng. Ví dụ:

```text
71. What does the man need to do first?
A. Change his clothes.
B. Attach a name tag.
C. Contact a warehouse supervisor.
D. Read an employee handbook.
```

Hệ thống hỗ trợ cách ghi như `Question 71:`, `(71)`, `A)`, `(A)`, `a:` và dòng xuống
hàng. Khi nhập một bộ đầy đủ đánh số cục bộ 1–39 hoặc 1–30, số hiển thị được đổi
theo Part 3 (32–70) hoặc Part 4 (71–100). Bảng đáp án vẫn có thể nhập theo số cục bộ
hoặc số TOEIC, không trộn hai cách trong cùng bảng.

Word được đọc trực tiếp trên máy chạy Django, không gọi OpenAI. Câu hỏi và lựa chọn
được lưu vào đề như nội dung đọc từ PDF, học viên chọn đáp án trên web. File Word
chỉ dùng trong lần nhập, không được công bố cho học viên hoặc lưu thành tài liệu
PDF. Nếu muốn cung cấp thêm PDF để đối chiếu, tải PDF và Word; hệ thống ưu tiên Word
khi đã chọn làm nguồn câu hỏi. Đáp án đúng vẫn được nhập riêng ở phần 2.

PDF có lớp chữ được đọc bằng PDF.js ngay trong trình duyệt, không gọi OpenAI.
Mỗi PDF nhập câu hỏi tối đa 40 trang; nên tách đúng phần cần giao. Cơ chế đọc hỗ trợ
bố cục một/hai cột và lựa chọn xuống dòng, nhưng giáo viên vẫn kiểm tra trước khi lưu.
Với PDF scan, nút nhận dạng gọi OpenAI bằng `OPENAI_API_KEY` và `OPENAI_TEXT_MODEL`
đã cấu hình trên máy chạy Django; có thể phát sinh phí API. Không cần train hay cài
thêm thư viện Python cho chức năng này. API key không được đưa ra trình duyệt.
Nhận dạng có thể sai khi ảnh mờ hoặc bố cục phức tạp; nội dung chưa rõ không được
tự điền thành lời giải. Chỉ bấm nhận dạng khi tài liệu cần dùng AI.

Dạng 1 có tranh và các lựa chọn trong audio; không cần tự tạo lời đọc không in trên đề.
Dạng 2 chỉ có file nghe, gồm câu 7–31 và ba lựa chọn A/B/C. Biểu mẫu ẩn PDF và phần
nhập câu hỏi in sẵn của dạng này; học viên nghe, chọn A/B/C rồi ghi câu trả lời ngắn.
Dạng 4 gồm 30 câu, đánh số 71–100 như TOEIC Part 4.
Dạng 3/4 cần câu hỏi và nội dung lựa chọn để học viên chọn ngay trên web; có thể nhập
bằng PDF, CSV đủ nội dung hoặc sửa trong trình soạn câu.

PDF được hiển thị trên web với nút chuyển trang, phóng to/thu nhỏ. Không cần tải về
để làm bài. Bộ xem PDF được đóng gói sẵn trong mã nguồn, không cần cài thêm Python
package hoặc tải thư viện từ CDN khi mở đề. Liên kết mở tab mới được giữ để xem rộng hơn.

Nếu chưa thấy nút thêm: chức năng này nằm ở giao diện giáo viên/admin/quản lý trong
ngân hàng bài tập. Buổi đã giao hoặc có bài làm sẽ hiển thị bốn dạng để tham khảo và
nút **Tạo bản sao để thêm bài tập**. Tạo bản sao rồi biên soạn, giao buổi mới; đề và
kết quả đã dùng trước đó được giữ nguyên. Buổi của giáo viên khác cũng có giải thích
quyền xem và nút sao chép. Khi đủ bốn bài, màn hình báo rõ giới hạn và vẫn có nút sửa,
xóa từng bài chưa giao.

### Kiểm tra trước khi giao

Trong biểu mẫu giao bài, chọn buổi và lớp để xem bảng kiểm tra bên cạnh. Hệ thống nêu
rõ số bài/câu, tài liệu, giáo viên phụ trách và số học viên nhận bài. Nếu buổi chưa có
bài nghe, hoặc bài/câu chưa đủ số câu, thiếu đáp án hay tài liệu, mở **Quản lý bài tập / bổ
sung nội dung** để sửa rồi quay lại. Dạng 2 chỉ cần A/B/C; PDF chỉ bắt buộc với dạng 1.
Thông báo “Mỗi câu nghe phải có lựa chọn và đáp án A–D…” trước đây là thông báo chung,
không cho biết buổi rỗng hay câu nào thiếu key. Bản mới tách các trường hợp này và chỉ rõ
bài/câu cần bổ sung; không tự đoán đáp án thay người soạn.

Chỉ hiện số lượt viết khi giao Vocabulary. Nhập giờ Việt Nam (UTC+7), bảo đảm hạn nộp
không trước thời điểm mở bài rồi bấm **Giao bài cho lớp**. Với cùng buổi và lớp đã giao,
biểu mẫu có liên kết **Mở lượt giao hiện có** để chỉnh hạn nộp; không tạo trùng bài.

## 3. Nhập đáp án thuận tiện

**Cách nhanh nhất: sao chép cột đáp án từ Excel rồi dán.** Ví dụ dạng 1 có sáu đáp án:

```text
A C B D A C
```

Có thể dán mỗi đáp án trên một dòng, hoặc dán kèm số câu:

```text
1.A 2.C 3.B 4.D 5.A 6.C
```

**Cách dùng file:** bấm **Tải mẫu CSV theo dạng bài**, mở bằng Excel, điền cột
`answer` rồi lưu **CSV UTF-8**. Không đổi số thứ tự, không bỏ dòng. Tải file đó vào
trường **Hoặc tải bảng đáp án CSV / TXT**. Ví dụ CSV tối giản:

```csv
number,answer
1,A
2,C
3,B
4,D
5,A
6,C
```

Khi tải file, hệ thống dùng nội dung file thay cho phần dán. Dạng 2 chỉ nhận A/B/C.
Số câu thiếu, trùng, ngoài phạm vi hoặc đáp án không hợp lệ sẽ báo lỗi trước khi lưu.
File CSV/TXT tối đa 1 MiB. Không tự dùng AI đoán đáp án từ audio hoặc PDF.

Nếu nhập nội dung đề/lựa chọn bằng CSV, dùng các cột
`question_text,A,B,C,D` trong mẫu. Nội dung chứa dấu phẩy phải đặt trong dấu nháy kép.
Nếu đã đọc và kiểm tra câu hỏi từ PDF, chỉ cần điền `number,answer`.
Mẫu CSV dùng số câu đã đọc từ PDF; có thể nhập key theo số trên
đề (ví dụ `32.B … 70.C`), theo thứ tự trong bài (`1.B … 39.C`) hoặc chỉ dán chuỗi chữ.
Không trộn hai cách đánh số trong cùng một bảng. Số câu trên PDF được lưu riêng với
thứ tự nội bộ, giữ đúng liên kết câu hỏi–lựa chọn–key khi chấm và xem kết quả.

## 4. Học viên làm bài và giáo viên theo dõi

Học viên chọn bài bằng các tab, phát audio, bấm số câu để làm lần lượt. Nội dung
câu hỏi và từng lựa chọn được hiển thị trực tiếp. Chọn một phương án bằng nút tròn
rồi ghi câu trả lời ngắn ở ô bên cạnh (trên điện thoại nằm ngay dưới lựa chọn), tối
đa 255 ký tự/câu. Dạng 1 hiển thị PDF tranh cùng phần trả lời; dạng 3/4 có nút
**Xem đề PDF** khi cần đối chiếu tài liệu gốc. Nút trước/tiếp theo đổi câu; dấu số
cho biết câu nào đã làm đủ. Chuyển bài/câu không xóa câu trả lời đã nhập.
Bộ đếm cho biết đã trả lời bao nhiêu câu. Cả lựa
chọn và câu trả lời ngắn được lưu nháp; có thể tải lại để tiếp tục trong hạn lưu nháp.
Vẫn cho phép nộp khi còn thiếu để ghi nhận đúng tình trạng bài đã làm.

Sau khi nộp, bài nghe được chấm ngay theo bảng đáp án đã giao, không gọi OpenAI.
Kết quả cho biết mức hoàn thành, từng câu đúng/sai, câu trả lời ngắn và các câu còn thiếu.
Bài thiếu có thể bổ sung và nộp lại nếu quy định nhận bài cho phép. Học viên chỉ xem
dữ liệu của mình; giáo viên chỉ xem/chấm lớp được phân công, admin xem toàn hệ thống.

Đối với bài đọc/từ vựng, giáo viên chọn **Hoàn thành · làm đủ yêu cầu** hoặc
**Chưa hoàn thành · cần bổ sung**, rồi bấm **Xác nhận kết quả**. AI chỉ đưa đề xuất
và bằng chứng; báo cáo và CSV dùng kết luận cuối cùng, không còn cột điểm.

### Nghe lại đúng vị trí

Trình phát giữ thanh kéo thời gian của trình duyệt và bổ sung **Lùi 10 giây**,
**Tiến 10 giây**, **Nghe từ đầu**, cùng ô nhập mốc `phút:giây` (ví dụ `02:30`)
và nút **Đi đến**. Có thể nhập `giờ:phút:giây` với file dài. Enter trong ô mốc
chỉ chuyển vị trí nghe, không nộp bài. Các nút chờ thông tin thời lượng trước khi bật.

Endpoint tệp đã được cấp quyền hỗ trợ HTTP byte ranges (206) để trình duyệt tải
đoạn cần nghe. Không cần tải hết file trước khi tua; quyền xem bài vẫn được kiểm tra
trước khi trả bất kỳ đoạn dữ liệu nào. Với bản ghi chưa có thời lượng đầy đủ, các
mốc chọn được giới hạn trong phần trình duyệt đã đọc được.

## 5. Cập nhật trên máy đang có dữ liệu

Sao lưu database và thư mục media cùng thời điểm, sau đó cập nhật đúng nhánh:

```powershell
git switch codex/mrbean-full-integration
git pull origin codex/mrbean-full-integration
python manage.py migrate
python manage.py check
```

Chạy các lệnh bằng Python của virtualenv đang dùng trong PyCharm. Không cần nâng cấp
`requirements.txt` cho thay đổi này. Khởi động lại website, AI worker và watchdog.
Nếu triển khai dùng static đã thu thập, chạy thêm `python manage.py collectstatic --noinput`.

Migration mới `assignments.0007` bổ sung số câu trên đề gốc, không viết lại snapshot
hay kết quả lịch sử. Điểm, nhận xét, bài làm và ID câu hỏi cũ được giữ nguyên. Các câu nghe
trong ngân hàng cũ được gom thành một bài **Bài nghe đã có**; không tự nhân thành bốn bài
hoặc ép đổi số câu của đề lịch sử. Trước khi giao lại nguồn cũ, bổ sung audio còn thiếu;
nên sao chép và tạo bài theo bốn dạng mới khi muốn chuẩn hóa nội dung.

Bài nghe lịch sử chỉ được suy ra đủ/thiếu từ các trường mà đề cũ thực sự yêu cầu,
không phạt thiếu câu trả lời ngắn chưa có trong đề cũ. Các bài đã chấm khác được giữ
điểm và chuyển sang **chờ xác nhận hoàn thành** nếu chưa có bằng chứng rõ ràng. Giáo
viên mở bài trong danh sách chờ, dùng **Lưu mức hoàn thành** để xác nhận đủ/thiếu mà
không nhập lại điểm hay nhận xét. Không tự đánh dấu hoàn thành chỉ vì điểm cao.

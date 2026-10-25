# Mr Bean — Dashboard ba vai trò và chấm bài tự động

## Phạm vi và nguồn tích hợp

Mọi thay đổi chỉ được đưa vào nhánh **`codex/ai-dashboard-bv`**. Không merge vào
`AI`, `master`, `assignments` hoặc `feature/setup-web-admin`.

Nguồn đọc (snapshot đã tích hợp vào chính nhánh này):

| Nguồn | Commit | Phần được tái sử dụng |
| --- | --- | --- |
| `feature/setup-web-admin` | `a2e0c37ed8e4e2a014679f0903738a450025b76c` | CustomUser, Notification, Course, ClassRoom, Enrollment, quota/miễn bài, forms, views, template chung và migrations |
| `assignments` | `0254880f397168a31132197d074db8231a30c9ef` | Lesson, VocabWord, ListeningQuestion, SpeakingTask, LessonProgress, QuestionResponse, SpeakingRecording, migrations và nguyên tắc chấm nghe |
| Nhánh dashboard trước tích hợp | `ecb4537eb3f77daebaf605630130aaaaa1bb6d12` | LearningTask, GradingJob, queue lưu DB, fallback và báo cáo |

Bổ sung `ClassAssignment` để nối buổi học với lớp; roster lấy từ `Enrollment`
thật, gồm cả người chưa nộp. Đề bài/đáp án/số lượt viết được snapshot khi giao,
không dùng yêu cầu hay điểm do client tự gửi. Mỗi lần nộp lưu một GradingJob
bất biến về bài làm, kể cả khi học viên nộp lại. `LessonProgress` và
`QuestionResponse` tiếp tục nhận cập nhật tương thích phần B.

Repository không chứa database sản xuất hoặc file audio/ảnh gốc. Việc lấy
model/migration và nội dung mẫu không đồng nghĩa đã sao chép dữ liệu thật từ
máy thành viên khác. Có lệnh seed local và lệnh nhập tiến độ đã tồn tại trong
DB (xem dưới).

## Chạy trên Windows PowerShell

Ở thư mục repository:

```powershell
git fetch origin
git switch codex/ai-dashboard-bv
git pull --ff-only origin codex/ai-dashboard-bv
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Nếu đã có DB, sao lưu trước khi migrate. Không xóa DB, không dùng `--fake`
để bỏ qua lỗi migration. Các migration nguồn được giữ lại và các field mới
được thêm bằng migration tiếp theo.

Mở `http://127.0.0.1:8000/` → dashboard / đăng nhập. Lần đầu chỉ có superuser,
có thể tạo lớp và người dùng trong giao diện quản trị hoặc dùng mẫu local.

### Dữ liệu mẫu đủ ba vai trò

```powershell
python manage.py seed_demo --password "LocalDemo-2026!"
```

Chỉ chạy khi `DJANGO_DEBUG=true`; tạo `demo_admin`, `demo_manager`,
`demo_teacher`, `demo_student`, `demo_student2`, lớp `DEMO-01` và 3 bài
nghe/nói/từ vựng đã giao. Mật khẩu ở trên là ví dụ cho môi trường local,
người chạy có thể chọn mật khẩu khác. Chạy lại không reset mật khẩu đã có,
không tạo trùng roster và không gọi OpenAI.

Nội dung mẫu từ phần B gồm Business English (Resilience, Customer, Deadline),
Self Introduction và hai câu TOEIC A–D. Mẫu nghe chưa kèm audio thật: giáo viên
bổ sung qua Sửa buổi học trước khi giao buổi mới. Hai lệnh seed cũ `seed_data`
và `seed_phanb` chuyển tới cùng lệnh an toàn này, cũng bắt buộc `--password`.

## Cấu hình API OpenAI để chấm bài

1. Tạo API key của dự án tại `https://platform.openai.com/api-keys` và thiết lập
   Billing/Usage của dự án theo tài khoản của bạn. Ứng dụng gọi OpenAI API bằng
   key của backend; không dùng cookie hoặc mật khẩu ChatGPT.
2. Mở file `.env` vừa sao chép, điền:

```dotenv
OPENAI_API_KEY=YOUR_API_KEY_HERE
OPENAI_TEXT_MODEL=gpt-4o-mini
OPENAI_TRANSCRIBE_MODEL=gpt-4o-mini-transcribe
DJANGO_DEBUG=true
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DJANGO_SECRET_KEY=YOUR_RANDOM_DJANGO_SECRET
```

`.env` được nạp bằng python-dotenv; biến môi trường có sẵn được ưu tiên.
Không commit key, không gửi key trong chat hoặc đưa key vào HTML/JavaScript.
Có thể tạo Django secret bằng:

```powershell
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

3. Kiểm tra cấu hình (không gọi API):

```powershell
python manage.py check_openai
```

4. Tùy chọn kiểm tra kết nối bằng yêu cầu nhỏ (có thể phát sinh phí API):

```powershell
python manage.py check_openai --live
```

5. Giữ web server và mở terminal thứ hai, cùng thư mục và virtualenv:

```powershell
.\.venv\Scripts\Activate.ps1
python manage.py run_ai_worker
```

Worker đọc `.env` lúc khởi động. Sau khi sửa key/model phải khởi động lại worker
và web server. `python manage.py run_ai_worker --once` xử lý tối đa một bài rồi
thoát. Không có worker thì bài chỉ nằm chờ; hết 5 phút phải qua watchdog để
chuyển manual.

6. Học viên nộp transcript/ảnh/text. Sau khi worker xử lý, vào kết quả bài nộp
để xem điểm AI gợi ý; giáo viên xác nhận điểm chính thức. Nghe không cần key
hay worker: chấm ngay bằng đáp án ở backend.

### Xử lý lỗi thường gặp

- `Chưa có OPENAI_API_KEY`: kiểm tra tên `.env` (không phải `.env.txt`), thư mục
  chứa `manage.py`, rồi restart worker.
- Key bị từ chối: tạo/kiểm tra key trong đúng project OpenAI.
- Hết quota/rate limit: kiểm tra Billing và Usage; lần nộp chuyển giáo viên,
  không retry API ẩn gây gọi lặp.
- Model không được cấp quyền hoặc JSON không hợp lệ: dùng model được project
  hỗ trợ, có Responses API / Structured Outputs; bài vẫn chuyển manual.
- Ảnh mờ, transcript rỗng hoặc lỗi mạng: giáo viên xem bài và chấm thủ công.

Tài liệu OpenAI đã dùng:
- https://developers.openai.com/api/docs/guides/structured-outputs
- https://developers.openai.com/api/docs/guides/speech-to-text
- https://developers.openai.com/api/docs/guides/images-vision

## Quy tắc chấm theo yêu cầu

### Nghe

Tái sử dụng model câu hỏi và nguyên tắc so đáp án của phần B. Luồng mới chỉ
cho giao bài nghe khi từng câu có A–D hợp lệ và lựa chọn đúng đã được cấu hình.
Bỏ trống tính sai; câu của bài khác bị từ chối. Điểm chính thức = số câu đúng /
tổng câu × 10; hoàn tất ngay, không gọi OpenAI. Không công khai correct_option
trong HTML/form/API đề bài học viên. Các câu part34 cũ không đủ lựa chọn A–D
phải được giáo viên bổ sung trước khi giao theo yêu cầu trắc nghiệm mới.

### Nói

Học viên nhập transcript, hoặc gửi audio để OpenAI tạo transcript rồi chấm.
Nếu gửi cả hai thì transcript nhập là nguồn được dùng và UI ghi rõ nguồn;
không khẳng định transcript nhập là bằng chứng đã nói đúng như audio.
Điểm AI = trung bình nội dung, từ vựng, ngữ pháp (mỗi tiêu chí 0–10).
**Không chấm phát âm, giọng, nét âm hoặc độ trôi chảy âm thanh.**
Audio WAV/MP3/M4A/WebM/MP4/OGG, tối đa 20 MiB. Không cần audio khi đã có
transcript. Transcript được lưu và hiển thị để giáo viên đối chiếu.

### Từ vựng

Giáo viên thiết lập từ phải viết và số lượt viết mỗi từ (1–100) lúc giao.
Học viên gửi text hoặc tối đa 5 ảnh JPEG/PNG/WebP, mỗi ảnh tối đa 8 MiB và
20 triệu điểm ảnh. Ảnh được kiểm tra, xoay theo EXIF và chuẩn hóa JPEG.
OpenAI đọc bài và trả số lượt quan sát của từng từ. Backend kiểm tra kiểu,
word thuộc rubric, không trùng, không âm và tính lại:

`matched = tổng min(số lượt quan sát từng từ, số lượt yêu cầu)`

`điểm AI = matched / tổng lượt yêu cầu × 10`

Ví dụ: 2 từ, mỗi từ 3 lượt → cần 6 lượt. Viết Customer 6 lần nhưng không viết
Deadline chỉ đáp ứng 3/6, không được tính là đủ. **Không chấm chữ đẹp/xấu**.
Ảnh trùng nội dung byte sau chuẩn hóa bị từ chối. Khi gửi cả ảnh và text, AI chỉ đếm trên ảnh để tránh cộng trùng bản chép.
Ảnh không rõ hoặc không chắc số lượt → manual, không đoán thành điểm 0/10.
Kết quả OCR/AI là gợi ý cần giáo viên kiểm tra; chống nhầm lẫn khi ảnh trùng
hoặc chứa cả bản in đề bài cần kiểm tra bằng dữ liệu thật trước vận hành.

### Điểm và fallback

AI tự tạo điểm gợi ý + nhận xét. Giáo viên phụ trách hoặc admin xác nhận
điểm cuối; manager theo dõi và giao bài, không xác nhận điểm. Nghe tự có
điểm chính thức. Điểm trung bình chính thức tách khỏi điểm trung bình AI.

Queue lưu DB; atomic claim tránh nhiều worker cùng chấm một bài. Deadline
300 giây tính từ lúc nộp, timeout mỗi tác vụ worker tối đa 120 giây và không
retry ẩn. Kết quả đến muộn không ghi đè manual hoặc điểm giáo viên.
Có thể chạy nhiều worker với PostgreSQL khi tải tăng.

Chạy watchdog `python manage.py expire_ai_jobs` bằng Task Scheduler mỗi phút
(Windows), hoặc cron/supervisor ở máy chủ, độc lập với worker. Watchdog có
sai số tối đa một chu kỳ; hạ tầng dừng thì không thể cam kết thời gian tuyệt
đối. Các mục SLA tiếp tục không hiển thị trên dashboard.

## Dashboard theo vai trò và luồng sử dụng

- **Admin/manager:** xem tổng hợp, lọc lớp/kỹ năng/tên/ngày giao, giao bài, xem tỷ lệ
  nộp, điểm, tiến độ từng học viên, học viên cần hỗ trợ và lịch sử.
- **Giáo viên:** chỉ xem dữ liệu lớp đang phụ trách; tạo buổi học của mình,
  giao cho lớp mình và chấm/duyệt. Giáo viên lớp khác không đọc bài hoặc media.
- **Học viên:** chỉ xem task/điểm/nhận xét của mình; làm nghe trắc nghiệm,
  gửi transcript/audio và bài từ vựng; nộp lại giữ lịch sử từng lần.

Các bảng báo cáo có phân trang 25 bản ghi, không giới hạn lịch sử ở 100 bài.
Polling 10 giây; dữ liệu rỗng/lỗi/phiên hết hạn được thông báo. Khi xác nhận
điểm thành công chuyển lại kết quả mới ngay. Giao diện dùng base.html được
nhập từ nhánh quản trị để thống nhất màu, font và điều hướng.

Tỷ lệ nộp = lượt giao đã có ít nhất một submission / toàn bộ lượt giao đến
thời điểm hiện tại. Không tính draft là đã nộp, không đếm trùng retry/nộp lại.
Trạng thái tiến độ theo lần nộp mới nhất; điểm theo lần nộp gần nhất đã chấm,
có chỉ báo riêng khi nộp lại đang chờ. Nguy cơ hỗ trợ: ít nhất 3 task quá hạn
chưa nộp, hoặc 7 ngày không nộp và còn task quá hạn (quy tắc, không phải ML).

Ghi danh qua service quản lý lớp tự thêm học viên vào các bài còn hạn. Nếu
đã chỉnh Enrollment qua admin hoặc nhập DB ngoài service, chạy:

```powershell
python manage.py sync_assignment_rosters
# Chỉ dùng khi chủ ý bổ sung cả bài đã hết hạn:
python manage.py sync_assignment_rosters --include-closed
```

Không tự xóa roster lịch sử khi học viên rời lớp. Học viên đã rời lớp được
xem lịch sử riêng nhưng không được nộp tiếp. Đổi giáo viên phụ trách lớp thay
đổi quyền xem/chấm theo lớp hiện tại; reviewed_by vẫn giữ người đã chấm.

## Dữ liệu tiến độ cũ của B đã có trong database

Sau migrate, nếu DB đang có LessonProgress hoàn thành và đã có ghi danh thật:

```powershell
python manage.py import_legacy_progress --classroom "YOUR-CLASS-CODE" --due-at "2026-10-30T23:59:00+07:00"
```

Hạn nộp do người vận hành cung cấp, không được suy đoán từ dữ liệu thiếu.
Lệnh tạo bài giao/roster và liên kết job với progress cũ, chạy lại không trùng.
Điểm nghe cũ thang 100 đổi sang 10, không chấm lại theo đáp án có thể đã sửa.
Bài nói/từ vựng cũ đưa manual vì không có đủ snapshot nội dung/ảnh và số lượt
viết tại thời điểm cũ. Teacher đối chiếu dữ liệu gốc; lệnh không tự gửi dữ liệu
cũ lên OpenAI. Chỉ nhập học viên đang ghi danh trong lớp chỉ định.

## Kiểm tra và triển khai

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

Test không gọi API thật: kiểm tra đủ ba vai trò, quyền lớp/học viên/media,
CSRF, snapshot rubric, nghe đúng/sai/bỏ trống, vocab thiếu lượt, transcript,
idempotency, timeout, fallback, phân trang và tích hợp các model nguồn.
Cần smoke test với key và bài làm thật để hiệu chỉnh rubric và độ chính xác
OCR/transcription. Không có tuyên bố AI đã được huấn luyện riêng.

Production: đặt DJANGO_DEBUG=false, secret riêng, hosts đúng, HTTPS,
PostgreSQL, storage riêng tư; không public thư mục `media/ai_submissions`.
File bài nộp chỉ đi qua endpoint có kiểm tra quyền. Không bật debug media
server công khai cho bài nộp. Chọn chính sách lưu trữ/xóa theo đơn vị vận hành.

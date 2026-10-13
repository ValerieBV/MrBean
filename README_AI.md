# Thành viên C — AI & Báo cáo (BV)

Nhánh nguồn: `AI`. Phạm vi: `ai_core`, `dashboard` và cấu hình URL/dependency.
Các app `assignments`, `submissions`, `courses` ở nhánh nguồn chưa có model,
cho nên dùng snapshot `LearningTask` để kết nối với Thành viên B, không tự thay
schema của các app đó. Cần nối adapter dưới đây vào luồng nộp bài của B khi tích hợp.

## Chạy

```sh
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
# Một tiến trình riêng, do supervisor/systemd quản lý:
python manage.py run_ai_worker
```

Đặt `OPENAI_API_KEY` trong môi trường tiến trình worker; `.env` không tự được đọc.
Mô hình cấu hình qua `OPENAI_TEXT_MODEL` (mặc định `gpt-4o-mini`) và
`OPENAI_AUDIO_MODEL` (mặc định `gpt-audio-1.5`). Không cần key để chạy kiểm thử.
Audio dùng Chat Completions với `input_audio`, trả text JSON, `store=False`:
https://developers.openai.com/api/docs/guides/audio-chat-completions

Đăng nhập tại `/accounts/login/`, dashboard tại `/dashboard/`. Tạo danh sách bài
được giao trong Django admin hoặc sync bằng code từ app B. Giáo viên chỉ thấy
bài mình phụ trách; manager/admin xem toàn hệ thống; học viên chỉ gửi/đọc bài
của chính mình và không được truy cập báo cáo.

Chạy watchdog độc lập mỗi phút để bài quá 5 phút chuyển sang chấm thủ công
kể cả worker bị treo hoặc dừng:

```cron
* * * * * cd /absolute/path/to/MrBean && /absolute/path/to/venv/bin/python manage.py expire_ai_jobs
```

`run_ai_worker --once` xử lý tối đa một bài. Queue nằm trong database, dùng
atomic compare-and-set để chỉ một worker nhận bài. Khi tải cao, dùng PostgreSQL
và nhiều worker. Worker mặc định timeout API 120 giây, không retry ẩn; hạn
300 giây tính từ lúc enqueue. Kết quả đến muộn không ghi đè hàng chấm thủ công
hoặc điểm giáo viên. Watchdog có sai số tối đa một chu kỳ chạy (~1 phút):
không có cam kết thời gian tuyệt đối khi hạ tầng dừng. Cần giám sát backlog và
bố trí đủ worker để AI có thể hoàn tất trước 5 phút.

## Hợp đồng tích hợp cho Thành viên B

Khi giao bài, sync **toàn bộ** roster, gồm cả học viên chưa nộp. Nếu chỉ tạo row
khi đã nộp, tỷ lệ nộp bài sẽ sai. `assignment_key` và `submission_key` là ID ổn
định từ app B, tối đa 128 ký tự. Mỗi lần nộp mới dùng submission key mới; retry
của cùng lần nộp dùng key cũ. Không đổi teacher/learner của task có lịch sử bài
nộp; tạo task mới hoặc triển khai luồng chuyển giao có phân quyền riêng.

```python
from django.db import transaction
from dashboard.models import LearningTask
from ai_core.services import enqueue_submission

with transaction.atomic():
    task, _ = LearningTask.objects.update_or_create(
        assignment_key=str(assignment.pk), learner=student,
        defaults={"title": assignment.title, "teacher": teacher,
                  "assigned_at": assignment.assigned_at, "due_at": assignment.due_at},
    )
    # Ngay trong transaction lưu bài nộp của B:
    job, created = enqueue_submission(
        task=task, submission_key=str(submission.pk),
        kind="speaking", audio=submission.audio,
        text="", reference_text=assignment.reference_text,
    )
```

Truyền `File`/`FieldFile` của Django hoặc `UploadedFile`; audio WAV/MP3 tối đa
20 MiB. Bài nói thiếu audio hoặc định dạng AI không hỗ trợ sẽ chấm thủ công,
không suy đoán phát âm từ transcript. Bài từ vựng cần `kind="vocabulary"`,
`text` không rỗng; pronunciation luôn null. Text/reference tối đa 20.000 ký tự.
Ứng dụng không chuyển đổi WebM/M4A: B cần đổi sang WAV/MP3 trước khi gửi nếu
muốn AI chấm. Audio chỉ được phát qua endpoint có kiểm tra quyền; không public
thư mục `media/ai_submissions` trong production.

API dự phòng cho client đã đăng nhập (Django session + CSRF, không phải
webhook công khai):

| Endpoint | Dữ liệu / hành vi |
| --- | --- |
| `POST /ai/submissions/` | JSON `task_id, submission_key, kind, text, reference_text`; hoặc multipart thêm `audio` |
| `GET /ai/jobs/<id>/` | Trạng thái, điểm gợi ý, điểm cuối và nhận xét; chỉ người có quyền với task |
| `GET /ai/jobs/<id>/audio/` | Audio riêng tư, cùng phạm vi quyền |
| `POST /ai/jobs/<id>/review/` | Giáo viên phụ trách / manager: JSON `score` 0–10 và `feedback` không rỗng |
| `GET /dashboard/metrics/` | Tỷ lệ nộp, điểm, trạng thái, SLA, nguy cơ và hàng chấm |

Lần enqueue đầu trả 201, callback lặp trả 200 cùng job. Key đã dùng cho task
khác trả 400. Auth thiếu: 401; vai trò không được phép: 403; bài ngoài phạm vi:
404; review bài chưa sẵn sàng hoặc đã chấm: 409. Phản hồi không hợp lệ: 400.

## Điểm & chỉ số

- AI chấm vocabulary/grammar, và pronunciation khi nghe được audio. JSON được
  kiểm tra kiểu dữ liệu, giá trị hữu hạn 0–10, nhận xét và yêu cầu chấm thủ công.
  Điểm gợi ý là trung bình các tiêu chí áp dụng; giáo viên xác nhận điểm cuối.
- AI lỗi, thiếu key, JSON sai, refusal, audio không dùng được hoặc quá hạn:
  chuyển `manual`; không lộ nội dung lỗi API ra giao diện/log.
- Tỷ lệ nộp = số task có ít nhất một bài / toàn bộ task đã giao. Retry và
  nộp nhiều lần không làm tăng mẫu số/tử số.
- Điểm trung bình giáo viên: mỗi task lấy lần chấm xác nhận gần nhất, bỏ qua
  task chưa chấm; điểm AI hiển thị riêng, mỗi task lấy gợi ý gần nhất.
- SLA 48 giờ tính từ mỗi lần nộp đến điểm giáo viên xác nhận. Cờ vàng từ giờ
  42 đến trước giờ 48; đỏ từ giờ 48. Bài AI đã nhận xét nhưng chưa duyệt vẫn
  thuộc SLA. `SLA_WARNING_HOURS` cấu hình trong settings.
- Nguy cơ: >= `DROPOUT_MISSED_TASKS` (3) task quá hạn chưa nộp; hoặc không
  nộp trong `DROPOUT_INACTIVE_DAYS` (7) ngày và còn task quá hạn chưa nộp.
  Học viên mới chưa có bài quá hạn không bị gắn cờ. Đây là quy tắc để giáo viên
  hỗ trợ, không phải dự đoán ML đã được hiệu chuẩn.
- Dashboard polling 10 giây, có thông báo khi tải lỗi; không phải WebSocket.
  Hàng chấm hiển thị 100 bài cũ nhất; duyệt sẽ đưa các bài tiếp theo lên.

## Kiểm thử

```sh
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test ai_core dashboard
```

Tests dùng provider giả lập: không gọi API trả phí. Cần smoke test với API key,
audio thật và rubric đã thống nhất trước khi vận hành. LLM đánh giá audio là
nhận xét gợi ý, không thay thế công cụ đo phát âm chuẩn hóa. Hạ tầng production
cần cấu hình Django secret/debug/hosts, database, file storage riêng tư và
supervisor theo môi trường triển khai.

## Báo cáo theo quy trình 7.1 / 7.2 / 7.3

- 7.1: `assigned_count`, `submitted_count`, `submission_rate` lấy từ roster D4
  và bài nộp D5. Dùng `dashboard.integration.sync_assignment_roster` khi giao
  bài để sync mọi học viên, kể cả chưa nộp. Hàm retry không tạo lượt giao trùng;
  không tự xóa học viên bị bỏ khỏi danh sách hoặc chuyển giáo viên của bài có
  lịch sử. App B vẫn cần gọi bridge vì chưa có model D4/D5 trong nhánh nguồn.
- 7.2: `graded_report` cung cấp điểm cuối, nhận xét giáo viên, người chấm và
  thời điểm xác nhận; `graded_count` đếm tất cả bài đã xác nhận.
- 7.3: `learner_progress` tổng hợp được giao, đã nộp, chưa nộp, chờ chấm,
  đã chấm, quá hạn chưa nộp và điểm trung bình theo học viên. Trạng thái theo
  lần nộp mới nhất; điểm theo lần nộp gần nhất đã chấm, có cột riêng cho nộp
  lại còn chờ. Các nhóm chưa nộp/chờ chấm/đã chấm cộng bằng số lượt giao.
- `sla_late_report` và `sla_late_count` giữ lịch sử bài được giáo viên xác nhận
  từ giờ 48 trở đi; không biến mất khi bài rời hàng chấm. SLA kết thúc ở lần
  giáo viên xác nhận. `finished_at` của bài graded là thời điểm xác nhận.
- Bảng điểm và lịch sử SLA hiển thị tối đa 100 bài mới nhất, kèm tổng số.
  Tiến độ và thống kê tổng lấy toàn bộ dữ liệu trong phạm vi quyền truy cập.

```python
from dashboard.integration import sync_assignment_roster

roster = sync_assignment_roster(
    assignment_key=str(assignment.pk), title=assignment.title, teacher=teacher,
    learners=assigned_students, assigned_at=assignment.assigned_at,
    due_at=assignment.due_at,
)
# Khi có bài nộp D5: lấy task đúng learner và gọi enqueue_submission như trên.
```

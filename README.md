# Mr Bean · Hệ thống quản lý học tập tiếng Anh

Nhánh tích hợp hoàn chỉnh: **`codex/mrbean-full-integration`**.

Ứng dụng Django gồm giao diện quản lý/admin, giáo viên và học viên; dùng chung tài khoản,
lớp học, ngân hàng bài tập, danh sách giao bài, kết quả và thông báo. Các nhánh nguồn
`AI`, `master`, `assignments`, `feature/setup-web-admin`, `codex/ai-dashboard-bv` được
đọc để tích hợp; không cập nhật ref hoặc gộp ngược vào các nhánh đó.

## 1. Cài đặt trên Windows PowerShell

Cần Git và Python 3.12 trở lên, phù hợp với phiên bản Django trong `requirements.txt`.

```powershell
git clone --branch codex/mrbean-full-integration https://github.com/ValerieBV/MrBean.git
cd MrBean
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Nếu đã có repository:

```powershell
git fetch origin
git switch --track origin/codex/mrbean-full-integration
```

Nếu nhánh đã tồn tại ở máy, dùng `git switch codex/mrbean-full-integration` rồi
`git pull --ff-only origin codex/mrbean-full-integration`. Lưu thay đổi cục bộ trước khi đổi nhánh.

Mở **http://127.0.0.1:8000/**. Superuser được nhận đúng vai trò admin trong giao diện.

Trên macOS/Linux, thay bước kích hoạt bằng `source .venv/bin/activate` và dùng
`cp .env.example .env`. Không ghi đè `.env` đã có.

## 2. Dùng dữ liệu mẫu

```powershell
python manage.py seed_demo --password "LocalDemo-2026!"
```

Chỉ chạy khi `DJANGO_DEBUG=true`. Tạo tài khoản `demo_admin`, `demo_manager`,
`demo_teacher`, `demo_student`, `demo_student2` với mật khẩu bạn nhập; lớp `DEMO-01`,
bài nghe trắc nghiệm và từ vựng đã giao. Chạy lại không đặt lại mật khẩu hoặc
sửa nội dung đang có. Các lệnh `seed_data`, `seed_phanb` vẫn dùng được với cùng
tham số `--password`.

Lệnh cũng giữ danh mục mẫu từ hai nhánh A/B: ba khóa học, hai lớp ở trạng thái
chưa hoạt động, các buổi từ vựng, TOEIC Part 1–4 và Self Introduction ở dạng nháp.
Có thể nhập riêng bằng `python manage.py seed_source_catalog --owner TEN_ADMIN`.
Không tạo tài khoản với mật khẩu yếu từ seed cũ. Nếu vị trí buổi học đã được dùng,
không chèn nội dung mẫu vào buổi đó.

Repository không có database sản xuất, video, audio hoặc bài nộp thật của các thành viên.
Mẫu nghe cần giáo viên bổ sung file nghe; mẫu đọc cần video thật và lời mẫu chính xác
trước khi bật và giao. Video cũ trong danh mục nguồn chỉ để tham khảo, chưa xác nhận
khớp lời đọc. Không dùng câu lệnh “Introduce yourself” làm lời mẫu.

## 3. Điền API key OpenAI ở đâu?

Mở **`.env` cùng thư mục với `manage.py`**, điền:

```dotenv
OPENAI_API_KEY=YOUR_OPENAI_API_KEY
OPENAI_TEXT_MODEL=gpt-6-luna
OPENAI_TRANSCRIBE_MODEL=gpt-transcribe
DJANGO_DEBUG=true
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DJANGO_SECRET_KEY=YOUR_RANDOM_DJANGO_SECRET
```

Tạo key trong dự án tại https://platform.openai.com/api-keys và cấu hình quyền/model,
Billing theo tài khoản API của bạn. Key chỉ được backend đọc, không xuất hiện trong HTML/JS.
Biến môi trường máy chủ được ưu tiên hơn `.env`. Không commit hoặc gửi key trong chat.

Kiểm tra cấu hình không gọi mạng:

```powershell
python manage.py check_openai
```

Mở thêm **hai terminal**, kích hoạt cùng virtualenv và chạy:

```powershell
# Terminal 2: xử lý AI
python manage.py run_ai_worker
```

```powershell
# Terminal 3: watchdog độc lập, vẫn hoạt động nếu worker bị dừng
python manage.py expire_ai_jobs --loop
```

Giữ terminal web `runserver` đang chạy. Khởi động lại cả web, worker, watchdog sau
khi đổi `.env`. `check_openai --live` là kiểm tra kết nối tùy chọn và có thể phát sinh phí;
nó không thay thế thử nghiệm chuyển âm thanh thành transcript hoặc đọc ảnh thật.

| Loại bài | Bài làm học viên | Cách chấm |
| --- | --- | --- |
| Listening | Chọn A/B/C/D | Backend so đáp án đã giao, trả điểm chính thức ngay |
| Đọc theo video / Speaking | Ghi âm trực tiếp bằng micro | OpenAI tạo transcript; backend so thứ tự từ với lời mẫu; AI nhận xét; giáo viên xác nhận |
| Vocabulary | Văn bản hoặc tối đa 5 ảnh bài chép | AI đếm lượt từng từ; backend tính điểm đủ số lượng; giáo viên xác nhận |

Không chấm phát âm, giọng hay chữ đẹp/xấu. Đây là prompt và quy tắc chấm có kiểm tra
đầu ra, **không phải mô hình đã fine-tune riêng**. Khi API lỗi, dữ liệu không chắc chắn
hoặc vượt hạn 300 giây, bài vào hàng chấm thủ công. Watchdog kiểm tra mỗi giây;
không cam kết độ trễ tuyệt đối khi máy chủ ngừng hoạt động. Nghe trắc nghiệm không cần API key/worker.

Chi tiết cấu hình, prompt, thang điểm, API và nhập kết quả cũ: [README_AI.md](README_AI.md).

## 4. Quy trình vận hành

Hỏi đáp sau khi có kết quả và mục liên hệ riêng đã có trong menu:
[Hướng dẫn hỏi AI, hỏi giáo viên và liên hệ quản lý](docs/AI_TUTOR_AND_CONTACT.md).

1. **Admin/quản lý:** tạo khóa → tạo lớp → phân công giáo viên → tạo tài khoản học viên → ghi danh.
2. **Giáo viên/admin/quản lý:** tạo buổi trong ngân hàng → thêm câu hỏi/đáp án, từ vựng hoặc video/lời mẫu → giao cho đúng lớp, đặt hạn và quy định nộp.
3. **Học viên:** xem bài của mình → làm theo thứ tự → lưu nháp nghe/từ vựng → nộp.
4. **Hệ thống:** chấm nghe ngay hoặc đưa vào AI; AI lỗi chuyển thủ công; lưu mọi lần nộp cùng đề đã dùng.
5. **Giáo viên đúng lớp/admin:** xem bản ghi/ảnh/transcript → xác nhận điểm, nhận xét và mức hoàn thành (đủ yêu cầu/còn thiếu).
6. **Học viên:** nhận thông báo → xem điểm/nhận xét/lịch sử → nộp lại nếu bài còn nhận.
7. **Quản lý:** theo dõi tỷ lệ hoàn thành, số đã nộp, điểm chính thức, tiến độ, tín hiệu học viên cần hỗ trợ; xuất CSV.

Nhánh có cả quản lý và admin như các model gốc. Quản lý tạo học viên, quản lý lớp,
giao bài và theo dõi; quyền thay vai trò, đặt lại mật khẩu và xác nhận điểm được tách rõ.

Xin miễn: chọn bài Speaking/Vocabulary chưa nộp → giáo viên duyệt đúng lớp → trừ
một lượt và loại bài khỏi số phải nộp. Listening luôn bắt buộc. Có thể hủy đơn đang chờ.
Hạn mức theo mã học viên: T/V 8 lượt, B 5 lượt, chưa có mã mặc định 8.

Bài nghe mỗi buổi tự thêm 1–4 bài theo bốn dạng 6/25/39/30 câu; có nhập đáp án hàng
loạt, PDF xem trực tiếp và câu trả lời ngắn. Chỉ bài đã chấm đủ yêu cầu mới tính hoàn
thành; nộp bài chưa đồng nghĩa hoàn thành. Xem [hướng dẫn sử dụng](docs/LISTENING_AND_COMPLETION.md).

Xem toàn bộ màn hình, quyền và trường hợp ngoại lệ ở [docs/WORKFLOWS.md](docs/WORKFLOWS.md).

## 5. Database và nâng cấp

Mặc định dùng SQLite tại `db.sqlite3`; có thể đặt `DJANGO_DB_PATH` để dùng file riêng.
Không đưa DB, `.env` hoặc `media/` lên Git. Model và migration gốc của các thành viên
được giữ, các thay đổi mới dùng migration tiếp theo.

Nếu đã có dữ liệu, sao lưu **DB và media cùng thời điểm** trước khi chạy `migrate`.
Không xóa DB, không dùng `--fake` để bỏ qua lỗi. Migration sẽ dừng và liệt kê ID nếu
một học viên đang active ở nhiều lớp; người quản lý cần xác định lớp active, chuyển
các ghi danh còn lại sang `completed`/`dropped` trong bản sao dữ liệu rồi nâng cấp.
Quá trình này giữ lịch sử; không tự chọn hoặc xóa ghi danh.

Kết quả từ database của phần B có thể nhập qua `import_legacy_progress`; xem
[README_AI.md](README_AI.md). Nhập dữ liệu thật từ máy khác cần có bản sao DB và
media được người giữ dữ liệu cung cấp; Git không chứa những dữ liệu này.

## 6. Kiểm thử và các giới hạn đã biết

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

Kiểm thử không gọi API có phí. Đã kiểm tra quyền theo lớp, CSRF, chấm nghe, chỉ nhận
bản ghi, snapshot đề, miễn bài, quota, lưu nháp, chuyển giáo viên, thống kê và nâng cấp DB.
Kiểm tra giao diện trên Chromium gồm luồng tạo lớp đến công bố điểm, menu ba vai trò,
mobile 390/768 px và kiểm tra truy cập tự động. Cách chạy lại: [docs/TESTING.md](docs/TESTING.md).

Cần thử nghiệm cuối với API key, video/lời mẫu và bài làm thật của trung tâm để đánh giá
độ chính xác nhận dạng giọng nói/ảnh và quyền model trong tài khoản. Bộ demo và kiểm thử
không chứng minh độ chính xác AI trên dữ liệu thật. Khi triển khai, dùng HTTPS để micro
hoạt động, giám sát cả ba tiến trình và giữ media riêng tư; `runserver` dành cho phát triển.

Thông tin nhánh nguồn và cách hòa giải code: [docs/INTEGRATION.md](docs/INTEGRATION.md).

Giao diện tích hợp các nhánh và luồng sử dụng: [Đối chiếu tích hợp ngày 27/10/2026](docs/INTEGRATION_REVIEW.md).

Bảng màu và cách đóng/mở thanh bên: [Hướng dẫn giao diện](docs/UI_PALETTE_AND_NAVIGATION.md).

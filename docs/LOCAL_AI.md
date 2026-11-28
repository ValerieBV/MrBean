# Dùng mô hình Colab trong MrBean

## Colab và OpenAI là hai phần độc lập

Colab chỉ dùng để huấn luyện và xuất checkpoint. Sau khi chép checkpoint về máy
chạy Django, website không cần Colab hoạt động. Không có kết nối Colab → OpenAI,
không đưa trọng số TrOCR/Whisper vào `OPENAI_TEXT_MODEL`, và không cần API key thứ
hai. Huấn luyện mô hình local không cập nhật trọng số của OpenAI.

Luồng hiện thực hiện:

1. Học viên nộp ảnh từ vựng hoặc ghi âm; Django lưu bài và đưa vào hàng đợi.
2. Worker tìm checkpoint local tương ứng. Nếu có đủ tệp và thư viện, TrOCR đọc
   các vùng chữ hoặc Whisper tạo bản chép bổ sung. Mô hình được lưu trong bộ nhớ
   worker để dùng lại, không tải lại cho từng vùng chữ.
3. Bài từ vựng: OpenAI luôn nhận ảnh gốc, yêu cầu bài và OCR local tham khảo.
   TrOCR không tự đếm lượt chép vì nội dung OCR có thể chứa cả nghĩa/ví dụ.
4. Bài nói: OpenAI vẫn tạo transcript chính từ ghi âm; nếu có Whisper local thì
   bản chép đó được gửi thêm để đối chiếu. Lời mẫu không được đưa vào prompt ASR.
5. Backend kiểm tra phản hồi, tính số lượt đã đáp ứng cho từng từ và lưu đề xuất
   hoàn thành. Các đề xuất đều chờ giáo viên kiểm tra và xác nhận trước khi cập
   nhật tiến độ chính thức. Hai bản transcript mâu thuẫn chưa xác minh được thì
   AI được yêu cầu để mức hoàn thành chưa xác định. Phản hồi từ vựng thiếu số
   lượt cho bất kỳ từ nào sẽ chuyển kiểm tra thủ công; không tự coi mục thiếu là 0.

OpenAI vẫn được gọi như trước; dùng thêm mô hình local không làm mất API key
hay tự giảm số yêu cầu API. Phần OCR bổ sung làm tăng dữ liệu đầu vào của lượt
nhận xét. Nếu muốn thử tắt phần local, đặt `AI_LOCAL_ENABLED=false` rồi khởi động
lại worker. Hỏi đáp AI và chấm bài nghe theo đáp án giữ nguyên luồng hiện có.

## Đặt checkpoint

Ví dụ dự án Windows tại `E:\MrBean`, đặt các tệp TrOCR trong:

```text
E:\MrBean\ai_models\vocabulary\best_model
```

Đặt Whisper trong `ai_models/speaking/best_model` nếu đã train mô hình nhận dạng
giọng nói. Thư mục `best_model` chứa **toàn bộ** tệp do `model.save_pretrained`
và `processor.save_pretrained` lưu, gồm `config.json`, `model.safetensors` (hoặc
index và toàn bộ shard), `preprocessor_config.json`, `tokenizer_config.json`
và các tệp tokenizer. Không đặt ZIP hoặc tệp Git LFS pointer thay cho trọng số.

Nếu bạn mới có TrOCR, cứ để thư mục Whisper chưa có. Bài nói vẫn dùng OpenAI.
`completion_model.joblib` là bộ phân loại thử nghiệm riêng; nó không phải
checkpoint TrOCR/Whisper và không được tự động nạp hoặc dùng để kết luận học
viên thiếu bài. Luồng hiện tại dùng OpenAI đề xuất và giáo viên xác nhận.

Các cấu hình mặc định, chỉ cần đổi khi đặt mô hình ở đường dẫn khác:

```dotenv
AI_LOCAL_ENABLED=true
AI_LOCAL_VOCAB_MODEL_DIR=ai_models/vocabulary/best_model
AI_LOCAL_SPEAKING_MODEL_DIR=ai_models/speaking/best_model
AI_LOCAL_DEVICE=auto
```

Đường dẫn tương đối luôn tính từ thư mục chứa `manage.py`, không phụ thuộc thư
mục terminal. `auto` dùng CUDA khi có GPU NVIDIA dùng được, còn lại dùng CPU.
GPU đã chọn trên Colab không trở thành GPU trên máy Django. Chưa có số đo tốc
độ của checkpoint người dùng thì chưa khẳng định đáp ứng được bao nhiêu bài.

## Cài và kiểm tra

Trong virtual environment của dự án:

```powershell
python -m pip install -r requirements.txt
python -m pip install -r requirements-local-ai.txt
python manage.py check_local_models --kind vocabulary --load --strict
```

`requirements-local-ai.txt` khóa Transformers `4.57.6` như notebook. Máy chỉ có
CPU nên cài torch CPU trước, rồi chạy lệnh requirements:

```powershell
python -m pip install "torch>=2.6,<3" --index-url https://download.pytorch.org/whl/cpu
```

Whisper local cần FFmpeg đọc các định dạng ghi âm của trình duyệt (WebM, OGG,
MP4). Cài FFmpeg trong PATH hoặc khai báo `AI_FFMPEG_BINARY` bằng đường dẫn tới
file chạy. Nếu chưa có, phần ASR chính của OpenAI vẫn hoạt động.

Lệnh kiểm tra mặc định chỉ đọc cấu hình và kiểm tra đủ tệp. `--load` thử nạp
trọng số thực, `--strict` trả lỗi nếu chưa sẵn sàng. Các lệnh này không gọi API:

```powershell
python manage.py check_local_models
python manage.py check_local_models --kind speaking --load --strict
python manage.py check_local_models --image "E:\MrBean\test_page.png"
python manage.py check_local_models --audio "E:\MrBean\test_recording.webm"
```

Hai lệnh cuối hiển thị nội dung tệp do bạn chỉ định, không lưu thành bài nộp hay
công bố kết quả. Dùng ảnh mới chưa xuất hiện trong train để kiểm tra khả năng
nhận dạng. Kết quả OCR không phải số lượt chép chính thức.

## Chạy website và worker

Terminal thứ nhất:

```powershell
python manage.py migrate
python manage.py runserver
```

Terminal thứ hai, cùng môi trường Python, cấu hình `.env`, database và media:

```powershell
python manage.py run_ai_worker --warm-models
```

`--warm-models` nạp checkpoint trước khi lấy bài trong hàng đợi. Sau khi đổi
checkpoint hoặc cấu hình hãy khởi động lại worker. Không đặt bước suy luận vào
request nộp bài của học viên. Không cần chạy lại các ô train trên Colab.

Sau khi nộp bài, giáo viên/admin xem đề xuất AI và mục **Bản nhận dạng bổ sung**.
Mục này chỉ xuất hiện khi mô hình local đã đọc được nội dung. Bản OCR vẫn được
giữ cho giáo viên nếu API nhận xét sau đó lỗi. Học viên không nhận dữ liệu OCR
nội bộ qua giao diện hoặc API kết quả, kể cả sau khi giáo viên xác nhận.

## Khi mô hình chưa hoạt động

- `missing`: kiểm tra đường dẫn và đã giải nén đủ thư mục `best_model`.
- `wrong_kind`: TrOCR phải nằm ở cấu hình từ vựng; Whisper ở cấu hình bài nói.
- `lfs_pointer`: chạy `git lfs pull` hoặc chép bộ tệp đầy đủ từ Drive.
- `dependencies`/`version`: cài requirements-local-ai trong đúng môi trường của
  worker, khóa Transformers đúng phiên bản rồi khởi động lại worker.
- `empty`/`partial`: OCR chưa đọc được hoặc chỉ đọc một phần. Không gán số lượt
  viết bằng 0, không tự kết luận học viên thiếu bài.
- API key lỗi/hết hạn mức/mạng lỗi: bài chuyển giáo viên theo luồng dự phòng;
  việc có mô hình local không thay thế key hoặc hạn mức của OpenAI.

Phần chia vùng chữ là thuật toán hỗ trợ, có thể bỏ sót ảnh nghiêng, nhiều cột,
chữ đè dòng hoặc ảnh mờ. Do đó OpenAI luôn xem ảnh gốc. Bản ghi quá 10 phút hoặc
quá thời gian xử lý local được bỏ qua ở nhánh bổ sung thay vì âm thầm cắt ngắn;
ASR OpenAI chính vẫn được gọi với tệp gốc. Cần kiểm thử checkpoint và bài nộp
thực trước khi khẳng định độ chính xác trong sử dụng thực tế.

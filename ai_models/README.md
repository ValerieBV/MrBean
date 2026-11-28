# Mô hình đã train trên Colab

Đặt **toàn bộ thư mục** `best_model` từ lần train muốn dùng tại:

- Từ vựng / TrOCR: `ai_models/vocabulary/best_model/`
- Giọng nói / Whisper: `ai_models/speaking/best_model/`

Trong `best_model` cần có cấu hình, trọng số `.safetensors`, cấu hình processor
và các tệp tokenizer đã được notebook lưu cùng mô hình. Không chỉ chép riêng
`model.safetensors`. Không đổi tên mô hình gốc thành `best_model` để thay cho
checkpoint đã train.

Cài phần suy luận tùy chọn trong cùng môi trường Python chạy worker:

```powershell
python -m pip install -r requirements-local-ai.txt
python manage.py check_local_models --kind vocabulary --load --strict
```

Máy chỉ có CPU có thể cài bản CPU trước khi cài requirements:

```powershell
python -m pip install "torch>=2.6,<3" --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r requirements-local-ai.txt
```

Nếu trọng số được lưu bằng Git LFS, sau khi clone/pull phải chạy `git lfs pull`.
Lệnh kiểm tra sẽ phát hiện tệp pointer chưa được tải thành trọng số. Không cần
commit lại các ảnh/âm thanh học viên hoặc API key để dùng mô hình.

Xem `docs/LOCAL_AI.md` để cấu hình, thử từng ảnh/ghi âm và hiểu luồng OpenAI.

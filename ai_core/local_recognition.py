"""Optional Colab checkpoints, used as evidence rather than a grading rule.

Nothing is downloaded by this module. Heavy libraries are imported only in the
worker, after a complete local checkpoint has been found. Original photos and
the existing OpenAI transcription remain the primary grading evidence.
"""
from functools import lru_cache
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import time

from django.conf import settings
from PIL import Image, ImageChops, ImageFilter, ImageOps


HINTS = {
    'disabled': 'Chưa bật mô hình đã huấn luyện; sử dụng OpenAI.',
    'missing': 'Chưa tìm thấy thư mục best_model; sử dụng OpenAI.',
    'incomplete': 'Thư mục mô hình thiếu cấu hình, trọng số hoặc processor/tokenizer; sử dụng OpenAI.',
    'lfs_pointer': 'Trọng số hiện chỉ là tệp Git LFS pointer. Cần tải đầy đủ bằng git lfs pull hoặc chép best_model từ Drive.',
    'wrong_kind': 'Loại mô hình không phù hợp với bài tập; kiểm tra đường dẫn best_model.',
    'dependencies': 'Cần cài requirements-local-ai.txt trong môi trường Python chạy worker.',
    'version': 'Mô hình local cần Transformers 4.57.6 như notebook đã train.',
    'device': 'Thiết bị được cấu hình chưa dùng được; chọn auto hoặc cpu và khởi động lại worker.',
    'ffmpeg': 'Chưa tìm thấy FFmpeg để đọc ghi âm; tiếp tục dùng transcript của OpenAI.',
    'audio_limit': 'Bản ghi vượt giới hạn nhận dạng local; tiếp tục dùng transcript của OpenAI thay vì cắt ngắn bài.',
    'timeout': 'Phần nhận dạng local đã hết thời gian; tiếp tục đánh giá bằng dữ liệu gốc.',
    'empty': 'Mô hình local chưa đọc được nội dung; không suy ra học viên làm thiếu.',
    'error': 'Chưa chạy được mô hình local; tiếp tục dùng OpenAI và giữ bài làm gốc.',
    'ready': 'Đã tìm thấy cấu hình, trọng số và processor/tokenizer.',
    'used': 'Đã dùng mô hình đã huấn luyện để cung cấp bằng chứng tham khảo.',
    'partial': 'Chỉ nhận dạng được một phần. Kết quả này không phải số lượt viết chính thức.',
}


class LocalRecognitionError(Exception):
    def __init__(self, code):
        self.code = code if code in HINTS else 'error'
        super().__init__(self.code)


def model_directory(kind):
    name = 'AI_LOCAL_VOCAB_MODEL_DIR' if kind == 'vocabulary' else 'AI_LOCAL_SPEAKING_MODEL_DIR'
    value = str(getattr(settings, name, '')).strip()
    if not value:
        return None
    path = Path(value).expanduser()
    return (path if path.is_absolute() else settings.BASE_DIR / path).resolve()


def _is_pointer(path):
    with path.open('rb') as stream:
        return stream.read(160).startswith(b'version https://git-lfs.github.com/spec/v1')


def inspect_model(kind):
    """Read configuration only; no torch import, model load, API or downloads."""
    path = model_directory(kind)
    status = {'kind': kind, 'path': str(path) if path else '', 'status': 'missing'}
    if not getattr(settings, 'AI_LOCAL_ENABLED', True):
        return {**status, 'status': 'disabled'}
    if path is None or not path.is_dir():
        return status
    try:
        config_path = path / 'config.json'
        if not config_path.is_file() or config_path.stat().st_size > 1024 * 1024:
            raise LocalRecognitionError('incomplete')
        config = json.loads(config_path.read_text(encoding='utf-8'))
        if not isinstance(config, dict):
            raise LocalRecognitionError('incomplete')
        valid = (config.get('model_type') == 'vision-encoder-decoder' and
                 config.get('decoder', {}).get('model_type') == 'trocr') if kind == 'vocabulary' else config.get('model_type') == 'whisper'
        if not valid:
            raise LocalRecognitionError('wrong_kind')
        if not (path / 'preprocessor_config.json').is_file() or not (path / 'tokenizer_config.json').is_file():
            raise LocalRecognitionError('incomplete')
        if not any((path / name).is_file() for name in ('tokenizer.json', 'sentencepiece.bpe.model', 'vocab.json')):
            raise LocalRecognitionError('incomplete')
        weights = [path / 'model.safetensors']
        index = path / 'model.safetensors.index.json'
        if index.is_file():
            if index.stat().st_size > 4 * 1024 * 1024:
                raise LocalRecognitionError('incomplete')
            manifest = json.loads(index.read_text(encoding='utf-8'))
            names = set(manifest.get('weight_map', {}).values())
            if not names or any(not isinstance(name, str) or Path(name).name != name or '\\' in name or not name.endswith('.safetensors') for name in names):
                raise LocalRecognitionError('incomplete')
            weights = [path / name for name in sorted(names)]
        for weight in weights:
            if not weight.is_file() or weight.stat().st_size < 16:
                raise LocalRecognitionError('incomplete')
            if _is_pointer(weight):
                raise LocalRecognitionError('lfs_pointer')
        # Cache identity includes weight stats, so replacing a checkpoint reloads it.
        identity = hashlib.sha256(config_path.read_bytes())
        for weight in weights:
            stat = weight.stat()
            identity.update(f'{weight.name}:{stat.st_size}:{stat.st_mtime_ns}'.encode())
        for asset in sorted(path.iterdir()):
            if asset.is_file() and asset.suffix in ('.json', '.model', '.txt'):
                stat = asset.stat()
                identity.update(f'{asset.name}:{stat.st_size}:{stat.st_mtime_ns}'.encode())
        return {**status, 'status': 'ready', 'cache_key': identity.hexdigest()}
    except LocalRecognitionError as exc:
        return {**status, 'status': exc.code}
    except (OSError, ValueError, TypeError, AttributeError):
        return {**status, 'status': 'incomplete'}


@lru_cache(maxsize=2)
def _load_model(kind, directory, cache_key, requested_device):
    try:
        import torch
        import transformers
        from transformers import TrOCRProcessor, VisionEncoderDecoderModel, WhisperProcessor, WhisperForConditionalGeneration
    except (ImportError, OSError):
        raise LocalRecognitionError('dependencies') from None
    if transformers.__version__ != '4.57.6':
        raise LocalRecognitionError('version')
    if requested_device not in ('auto', 'cpu', 'cuda') or requested_device == 'cuda' and not torch.cuda.is_available():
        raise LocalRecognitionError('device')
    device = 'cuda' if requested_device == 'auto' and torch.cuda.is_available() else 'cpu' if requested_device == 'auto' else requested_device
    options = {'local_files_only': True, 'trust_remote_code': False}
    if kind == 'vocabulary':
        processor = TrOCRProcessor.from_pretrained(directory, **options)
        model = VisionEncoderDecoderModel.from_pretrained(directory, use_safetensors=True, attn_implementation='eager', **options)
        # Respect saved token IDs. Fall back to decoder config only when absent.
        for name in ('decoder_start_token_id', 'pad_token_id', 'eos_token_id'):
            value = getattr(model.generation_config, name, None)
            if value is None:
                value = getattr(model.config, name, None)
            if value is None:
                value = getattr(model.config.decoder, name, None)
            if value is None:
                raise LocalRecognitionError('incomplete')
            setattr(model.generation_config, name, value)
    else:
        processor = WhisperProcessor.from_pretrained(directory, **options)
        model = WhisperForConditionalGeneration.from_pretrained(directory, use_safetensors=True, attn_implementation='eager', **options)
        model.generation_config.language = 'en'
        model.generation_config.task = 'transcribe'
        model.generation_config.forced_decoder_ids = None
    model.to(device)
    model.eval()
    if hasattr(model, 'gradient_checkpointing_disable'):
        model.gradient_checkpointing_disable()
    return processor, model, device


def load_local_model(kind):
    info = inspect_model(kind)
    if info['status'] != 'ready':
        raise LocalRecognitionError(info['status'])
    return _load_model(kind, info['path'], info['cache_key'], getattr(settings, 'AI_LOCAL_DEVICE', 'auto'))


def _remaining(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise LocalRecognitionError('timeout')
    return remaining


def _runs(values, max_gap=0):
    """Intervals over an ink projection; merging small gaps preserves strokes."""
    intervals = []
    for index, active in enumerate(values):
        if active:
            if intervals and index - intervals[-1][1] <= max_gap:
                intervals[-1][1] = index + 1
            else:
                intervals.append([index, index + 1])
    return intervals


def line_regions(image):
    """Heuristic crops for OCR assistance, never a claim of page completeness."""
    import numpy as np
    small = image.copy()
    small.thumbnail((1800, 2400))
    gray = ImageOps.grayscale(small)
    background = gray.filter(ImageFilter.GaussianBlur(12))
    difference = np.asarray(ImageChops.subtract(background, gray), dtype=np.uint8)
    ink = difference > 18
    # Notebook rules/borders are removed from the projection, not from the photo.
    ink[ink.mean(axis=1) > 0.65, :] = False
    ink[:, ink.mean(axis=0) > 0.85] = False
    row_mask = ink.sum(axis=1) >= max(2, small.width * 0.002)
    rows = _runs(row_mask, max_gap=3)
    scale_x, scale_y = image.width / small.width, image.height / small.height
    boxes = []
    for top, bottom in rows:
        height = bottom - top
        if height < 5:
            continue
        columns = _runs(ink[top:bottom].sum(axis=0) > 0, max_gap=max(12, int(height * 1.5)))
        for left, right in columns:
            if right - left < 5:
                continue
            pad = max(4, int(height * 0.15))
            boxes.append((max(0, int((left-pad)*scale_x)), max(0, int((top-pad)*scale_y)),
                          min(image.width, int((right+pad)*scale_x)), min(image.height, int((bottom+pad)*scale_y))))
    return boxes


def recognize_image(image, deadline, max_crops=None):
    """Read a photo with the saved processor, preserving case and word mistakes."""
    import torch
    processor, model, device = load_local_model('vocabulary')
    image = ImageOps.exif_transpose(image).convert('RGB')
    regions = line_regions(image)
    limit = max_crops if max_crops is not None else settings.AI_LOCAL_MAX_CROPS
    texts = []
    limited = len(regions) > limit
    for box in regions[:limit]:
        budget = _remaining(deadline)
        pixels = processor(images=image.crop(box), return_tensors='pt').pixel_values.to(device)
        with torch.inference_mode():
            ids = model.generate(pixels, num_beams=1, max_new_tokens=settings.AI_LOCAL_MAX_TOKENS, max_time=budget)
        text = processor.batch_decode(ids, skip_special_tokens=True)[0].strip()
        texts.append({'text': text[:512], 'box': list(box)})
    return texts, limited


def _decode_audio(data, deadline):
    """Browser WebM/OGG/MP4 and MP3 -> mono 16 kHz, without silent truncation."""
    import numpy as np
    executable = shutil.which(getattr(settings, 'AI_FFMPEG_BINARY', 'ffmpeg'))
    if not executable:
        raise LocalRecognitionError('ffmpeg')
    try:
        result = subprocess.run([executable, '-nostdin', '-hide_banner', '-loglevel', 'error',
            '-i', 'pipe:0', '-vn', '-t', str(settings.AI_LOCAL_MAX_AUDIO_SECONDS + 1),
            '-ac', '1', '-ar', '16000', '-f', 'f32le', 'pipe:1'],
            input=data, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=_remaining(deadline), check=True)
    except subprocess.TimeoutExpired:
        raise LocalRecognitionError('timeout') from None
    samples = np.frombuffer(result.stdout, dtype='<f4').copy()
    if samples.size > settings.AI_LOCAL_MAX_AUDIO_SECONDS * 16000:
        raise LocalRecognitionError('audio_limit')
    if not samples.size or not np.isfinite(samples).all():
        raise LocalRecognitionError('empty')
    return samples


def recognize_audio(data, deadline):
    import torch
    processor, model, device = load_local_model('speaking')
    samples = _decode_audio(data, deadline)
    # Whisper long-form generation reads the whole recording. Do not truncate
    # at its 30-second encoder window or feed the reference as an ASR prompt.
    features = processor.feature_extractor(samples, sampling_rate=16000,
        return_tensors='pt', return_attention_mask=True, truncation=False, padding='longest')
    inputs = {key: value.to(device) for key, value in features.items()}
    with torch.inference_mode():
        ids = model.generate(**inputs, language='en', task='transcribe',
            return_timestamps=True, num_beams=1, max_new_tokens=min(440, model.config.max_target_positions - 8), max_time=_remaining(deadline))
    text = processor.batch_decode(ids, skip_special_tokens=True)[0].strip()
    if not text or len(text) > 20000:
        raise LocalRecognitionError('empty')
    return text


def collect_local_evidence(job, seconds):
    """Fail open to original evidence, never interpret an OCR failure as zero."""
    kind = job.kind
    info = inspect_model(kind)
    report = {'kind': kind, 'status': info['status'], 'used': False, 'advisory_only': True}
    if info['status'] != 'ready':
        report['hint'] = HINTS[info['status']]
        return report
    deadline = time.monotonic() + max(0.0, seconds)
    try:
        if kind == 'vocabulary':
            lines, partial = [], False
            for number, page in enumerate(job.pages.order_by('pk'), 1):
                _remaining(deadline)
                left = settings.AI_LOCAL_MAX_CROPS - len(lines)
                if left <= 0:
                    partial = True
                    break
                with page.image.open('rb') as stream:
                    data = stream.read(settings.AI_MAX_IMAGE_BYTES + 1)
                if len(data) > settings.AI_MAX_IMAGE_BYTES:
                    raise LocalRecognitionError('error')
                with Image.open(io.BytesIO(data)) as image:
                    rows, limited = recognize_image(image, deadline, left)
                partial = partial or limited
                for row in rows:
                    if sum(len(item['text']) for item in lines) + len(row['text']) > 16000:
                        partial = True
                        break
                    lines.append({'page': number, **row})
            report.update(lines=lines, text='\n'.join(row['text'] for row in lines)[:16000],
                recognizer='local_trocr', exhaustive=False)
            report['status'] = 'partial' if partial else 'used' if report['text'].strip() else 'empty'
        else:
            with job.audio.open('rb') as stream:
                data = stream.read(settings.AI_MAX_AUDIO_BYTES + 1)
            if not data or len(data) > settings.AI_MAX_AUDIO_BYTES:
                raise LocalRecognitionError('error')
            report.update(text=recognize_audio(data, deadline), recognizer='local_whisper', status='used')
        report['used'] = bool(report.get('text', '').strip())
    except LocalRecognitionError as exc:
        report['status'] = exc.code
    except (ImportError, ModuleNotFoundError):
        report['status'] = 'dependencies'
    except Exception:
        # Paths, raw model errors and submission contents are not logged.
        report['status'] = 'error'
    report['hint'] = HINTS[report['status']]
    return report


def public_recognition_report(report):
    """Allowlisted model evidence for staff; excludes filesystem paths/config."""
    if not isinstance(report, dict) or report.get('status') not in HINTS:
        return None
    clean = {key: report[key] for key in ('kind', 'status', 'used', 'advisory_only', 'recognizer', 'exhaustive') if key in report}
    clean['hint'] = HINTS[report['status']]
    clean['text'] = str(report.get('text', ''))[:20000]
    return clean

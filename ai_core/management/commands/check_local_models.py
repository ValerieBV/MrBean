"""Inspect or test user-supplied checkpoints without calling any paid API."""
import time
from django.core.management.base import BaseCommand, CommandError
from PIL import Image
from ai_core.local_recognition import HINTS, LocalRecognitionError, inspect_model, load_local_model, recognize_image, recognize_audio


class Command(BaseCommand):
    help = 'Kiểm tra mô hình Colab trên máy; không gọi OpenAI. --load thử nạp trọng số, --image/--audio thử nhận dạng tệp chỉ định.'

    def add_arguments(self, parser):
        parser.add_argument('--kind', choices=['all', 'vocabulary', 'speaking'], default='all')
        parser.add_argument('--load', action='store_true')
        parser.add_argument('--strict', action='store_true', help='Báo lỗi khi mô hình được chọn chưa sẵn sàng')
        parser.add_argument('--image', help='Đường dẫn ảnh từ vựng do bạn chọn để thử')
        parser.add_argument('--audio', help='Đường dẫn ghi âm do bạn chọn để thử')

    def handle(self, *args, **options):
        if options['image'] and options['audio']:
            raise CommandError('Mỗi lần chỉ thử một ảnh hoặc một ghi âm.')
        kind = 'vocabulary' if options['image'] else 'speaking' if options['audio'] else options['kind']
        kinds = ['vocabulary', 'speaking'] if kind == 'all' else [kind]
        self.stdout.write('Chỉ kiểm tra mô hình local; không gọi API OpenAI và không chấm bài học viên.')
        failures = []
        for current in kinds:
            info = inspect_model(current)
            label = 'Từ vựng / TrOCR' if current == 'vocabulary' else 'Bài nói / Whisper'
            self.stdout.write(f'{label}: {info["path"] or "chưa đặt đường dẫn"}')
            self.stdout.write(f'  {info["status"]}: {HINTS[info["status"]]}')
            if info['status'] != 'ready':
                failures.append(current)
                continue
            if options['load'] or options['image'] or options['audio']:
                try:
                    _, _, device = load_local_model(current)
                    self.stdout.write(self.style.SUCCESS(f'  Đã nạp mô hình trên {device}.'))
                    deadline = time.monotonic() + 120
                    if options['image']:
                        with Image.open(options['image']) as image:
                            rows, limited = recognize_image(image, deadline)
                        self.stdout.write('Nội dung OCR tham khảo:')
                        for number, row in enumerate(rows, 1):
                            self.stdout.write(f'  {number}. {row["text"]}')
                        if limited:
                            self.stdout.write('Chỉ nhận dạng một phần do giới hạn số vùng chữ.')
                        self.stdout.write('Không dùng số vùng hoặc số từ OCR làm số lượt viết chính thức.')
                    if options['audio']:
                        from pathlib import Path
                        from django.conf import settings
                        path = Path(options['audio'])
                        if path.stat().st_size > settings.AI_MAX_AUDIO_BYTES:
                            raise LocalRecognitionError('error')
                        self.stdout.write('Transcript tham khảo: ' + recognize_audio(path.read_bytes(), deadline))
                except LocalRecognitionError as exc:
                    failures.append(current)
                    self.stderr.write(HINTS[exc.code])
                except Exception:
                    failures.append(current)
                    self.stderr.write('Không nạp/đọc được mô hình hoặc tệp thử. Kiểm tra đầy đủ best_model và các phiên bản thư viện.')
        if failures and (options['strict'] or options['image'] or options['audio']):
            raise CommandError('Mô hình chưa sẵn sàng: ' + ', '.join(failures))

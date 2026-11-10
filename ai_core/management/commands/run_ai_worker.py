import time
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from ai_core.models import GradingJob
from ai_core.services import expire_jobs, process_job
from ai_core.diagnostics import diagnostic_code


class Command(BaseCommand):
    help = 'Process durable AI queue; supervise alongside web server.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true')
        parser.add_argument('--warm-models', action='store_true', help='Nạp trước mô hình Colab để không phải chờ tải trọng số trong bài đầu tiên')

    def handle(self, *args, **options):
        self.stdout.write('Tiến trình chấm AI đã khởi động; Ctrl+C để dừng.')
        if not settings.OPENAI_API_KEY:
            self.stdout.write(self.style.WARNING('Tiến trình chưa nhận OPENAI_API_KEY. Kiểm tra .env và khởi động lại worker; bài xử lý lúc này sẽ chuyển chấm thủ công.'))
        if options['warm_models']:
            from ai_core.local_recognition import HINTS, LocalRecognitionError, inspect_model, load_local_model
            for kind in ('vocabulary', 'speaking'):
                info = inspect_model(kind)
                if info['status'] != 'ready':
                    self.stdout.write(f'{kind}: {HINTS[info["status"]]}')
                    continue
                try:
                    _, _, device = load_local_model(kind)
                    self.stdout.write(self.style.SUCCESS(f'{kind}: đã nạp mô hình Colab trên {device}.'))
                except LocalRecognitionError as exc:
                    self.stdout.write(self.style.WARNING(f'{kind}: {HINTS[exc.code]}'))
                except Exception:
                    self.stdout.write(self.style.WARNING(f'{kind}: {HINTS["error"]}'))
        try:
            while True:
                close_old_connections()
                expired = expire_jobs()
                if expired:
                    self.stdout.write(self.style.WARNING(f'{expired} bài đã quá 5 phút và chuyển sang chấm thủ công.'))
                job_id = GradingJob.objects.filter(status='queued').values_list('pk', flat=True).first()
                if job_id:
                    self.stdout.write(f'Đang xử lý bài #{job_id}.')
                    if process_job(job_id):
                        job = GradingJob.objects.filter(pk=job_id).first()
                        if job is None:
                            self.stdout.write(f'Bài #{job_id} đã được xóa; tiếp tục xử lý hàng đợi.')
                        elif job.status == 'ai_reviewed':
                            self.stdout.write(self.style.SUCCESS(f'Bài #{job_id}: AI đã đánh giá, chờ giáo viên xác nhận.'))
                        elif job.status == 'manual':
                            self.stdout.write(self.style.WARNING(f'Bài #{job_id}: chuyển chấm thủ công; nguyên nhân={diagnostic_code(job.fallback_reason)}.'))
                if options['once']:
                    return
                if not job_id:
                    time.sleep(1)
        except KeyboardInterrupt:
            self.stdout.write('Worker stopped; interrupted jobs expire into manual queue.')

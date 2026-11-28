"""Read-only local diagnostics; no calls to OpenAI and no submission contents."""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count
from ai_core.diagnostics import FALLBACK_HINTS, diagnostic_code
from ai_core.models import GradingJob


class Command(BaseCommand):
    help = 'Kiểm tra trạng thái và nguyên nhân chấm AI; chỉ đọc DB, không gọi API hoặc hiển thị key/bài làm.'

    def add_arguments(self, parser):
        parser.add_argument('--job', type=int, help='Chỉ kiểm tra mã bài nộp cụ thể')

    def handle(self, *args, **options):
        self.stdout.write('Chỉ đọc database; không gọi OpenAI hoặc tự chấm lại bài.')
        self.stdout.write('API key trong tiến trình kiểm tra: ' + ('đã có' if settings.OPENAI_API_KEY else 'chưa có'))
        jobs = GradingJob.objects.all()
        if options['job'] is not None:
            job = jobs.filter(pk=options['job']).first()
            if job is None:
                raise CommandError('Không tìm thấy bài nộp theo mã này.')
            self.stdout.write(f'Bài #{job.pk}: trạng thái={job.status}; loại={job.kind}')
            if job.status == 'manual':
                reason = diagnostic_code(job.fallback_reason)
                self.stdout.write(f'Nguyên nhân={reason}: {FALLBACK_HINTS[reason]}')
            elif job.status == 'ai_reviewed':
                self.stdout.write('AI đã đánh giá thành công. Bài đang chờ giáo viên xác nhận mức hoàn thành.')
            elif job.status in ('queued', 'processing'):
                self.stdout.write('Bài chưa hoàn tất AI. Giữ run_ai_worker và expire_ai_jobs --loop chạy cùng website.')
            elif job.status == 'graded':
                self.stdout.write('Bài đã có kết quả đánh giá.')
            return
        counts = {row['status']: row['total'] for row in jobs.values('status').annotate(total=Count('pk'))}
        for status, label in [('queued', 'Chờ AI'), ('processing', 'AI đang xử lý'),
                              ('ai_reviewed', 'AI đã đánh giá, chờ xác nhận'), ('manual', 'Cần chấm thủ công'),
                              ('graded', 'Đã xác nhận kết quả')]:
            self.stdout.write(f'{status}: {counts.get(status, 0)} — {label}')
        for row in jobs.filter(status='manual').values('fallback_reason').annotate(total=Count('pk')):
            reason = diagnostic_code(row['fallback_reason'])
            self.stdout.write(f'Nguyên nhân {reason}: {row["total"]} bài. {FALLBACK_HINTS[reason]}')
        self.stdout.write('Lệnh này không xác minh worker có đang chạy. Dùng --job MA_BAI để xem riêng; bài thủ công cũ không tự được chấm lại khi đổi key.')

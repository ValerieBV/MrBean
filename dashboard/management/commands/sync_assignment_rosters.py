from django.core.management.base import BaseCommand
from django.utils import timezone
from assignments.models import ClassAssignment
from dashboard.integration import sync_class_assignment


class Command(BaseCommand):
    help = 'Bổ sung roster từ Enrollment thực tế; mặc định chỉ bài còn hạn.'

    def add_arguments(self, parser):
        parser.add_argument('--include-closed', action='store_true')

    def handle(self, *args, **options):
        assignments = ClassAssignment.objects.all()
        if not options['include_closed']:
            assignments = assignments.filter(due_at__gte=timezone.now())
        count = 0
        for assignment in assignments.select_related('classroom','lesson'):
            count += len(sync_class_assignment(assignment))
        self.stdout.write(f'Đã đồng bộ {count} lượt giao; không xóa lịch sử.')

"""Explicit, idempotent import of B's completed progress already in the local DB."""
from datetime import timedelta
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from assignments.models import ClassAssignment
from assignments.services import assign_to_class
from courses.models import ClassRoom
from submissions.models import LessonProgress
from ai_core.models import GradingJob
from dashboard.integration import sync_class_assignment


class Command(BaseCommand):
    help = 'Nhập tiến độ cũ của B theo lớp xác định và hạn nộp do người vận hành cung cấp; không gọi AI.'

    def add_arguments(self, parser):
        parser.add_argument('--classroom', required=True, help='Mã lớp đang chứa học viên')
        parser.add_argument('--due-at', required=True, help='ISO datetime có múi giờ; không tự suy đoán hạn cũ')

    @transaction.atomic
    def handle(self, *args, **options):
        due = parse_datetime(options['due_at'])
        if not due or timezone.is_naive(due):
            raise CommandError('due-at phải có múi giờ, ví dụ 2026-10-30T23:59:00+07:00')
        classroom = ClassRoom.objects.filter(class_code=options['classroom']).first()
        if not classroom or not classroom.teacher_id:
            raise CommandError('Không tìm thấy lớp có giáo viên.')
        rows = LessonProgress.objects.filter(student__class_enrollments__classroom=classroom,
            student__class_enrollments__status='active', status='completed').select_related('student','lesson').order_by('started_at','pk')
        count = 0
        for progress in rows:
            key=f'legacy-progress:{progress.pk}'
            if GradingJob.objects.filter(submission_key=key).exists():
                continue
            assignment = ClassAssignment.objects.filter(classroom=classroom, lesson=progress.lesson).first()
            if not assignment:
                if due < progress.started_at:
                    raise CommandError('Hạn nhập không thể trước thời điểm bắt đầu bài cũ.')
                try:
                    assignment = assign_to_class(actor=classroom.teacher, lesson=progress.lesson, classroom=classroom,
                        assigned_at=progress.started_at, due_at=due)
                except Exception as exc:
                    raise CommandError('Bài cũ thiếu cấu hình hợp lệ; bổ sung yêu cầu/đáp án trước khi nhập: '+str(progress.lesson_id)) from exc
            task = next((t for t in sync_class_assignment(assignment) if t.learner_id == progress.student_id), None)
            if not task:
                continue
            # Preserve stored B score (0–100) instead of regrading against potentially edited keys.
            score = progress.score
            valid_score = isinstance(score,(int,float)) and 0 <= score <= 100 and progress.lesson.skill=='listening'
            GradingJob.objects.create(task=task, progress=progress, submission_key=key, kind=progress.lesson.skill,
                rubric_snapshot=assignment.rubric, submitted_at=progress.completed_at or progress.started_at,
                status='graded' if valid_score else 'manual', final_score=round(score/10,2) if valid_score else None,
                grading_method='legacy_import', fallback_reason='' if valid_score else 'legacy_needs_review',
                teacher_feedback='Điểm nhập từ tiến độ cũ (thang 100 đổi sang 10).' if valid_score else '',
                finished_at=progress.completed_at if valid_score else timezone.now())
            count += 1
        self.stdout.write(f'Đã nhập {count} bài cũ. Bài nói/từ vựng cũ không tự có điểm; giáo viên cần đối chiếu dữ liệu gốc.')

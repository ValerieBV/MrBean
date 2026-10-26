"""One authoritative submission policy shared by pages, drafts and APIs."""
from django.core.exceptions import ValidationError
from django.utils import timezone
from courses.models import Enrollment, ExemptionRequest
from dashboard.models import LearningTask


def is_unlocked(task, now=None):
    if not task.assignment_id or not task.assignment.requires_previous:
        return True
    now = now or timezone.now()
    lesson = task.assignment.lesson
    earlier = LearningTask.objects.filter(learner_id=task.learner_id,
        assignment__classroom_id=task.assignment.classroom_id, assignment__is_active=True,
        assignment__lesson__skill=lesson.skill, assignment__lesson__program=lesson.program,
        assignment__lesson__order__lt=lesson.order, assigned_at__lte=now, exemption__isnull=True)
    return not earlier.filter(jobs__isnull=True).exists()


def submission_problem(task, now=None):
    now = now or timezone.now()
    if not task.assignment_id:
        return 'Bài lịch sử chỉ dùng để tra cứu kết quả.'
    assignment = task.assignment
    if not assignment.is_active:
        return 'Lượt giao này đã tạm dừng nhận bài.'
    if not assignment.classroom.is_active:
        return 'Lớp học đã ngừng hoạt động.'
    if not task.learner.is_active or not Enrollment.objects.filter(classroom=assignment.classroom,
            student_id=task.learner_id, status='active').exists():
        return 'Bạn không còn ghi danh hoạt động trong lớp này.'
    if task.assigned_at > now:
        return 'Bài chưa đến thời điểm được mở.'
    if task.exemption_id:
        return 'Bạn đã được miễn bài này.'
    if ExemptionRequest.objects.filter(assignment=assignment, enrollment__student_id=task.learner_id, status='pending').exists():
        return 'Đơn miễn bài đang chờ duyệt. Hãy hủy đơn nếu bạn muốn nộp bài.'
    if not assignment.allow_late_submission and task.due_at < now:
        return 'Bài đã hết hạn và không nhận nộp muộn.'
    if not is_unlocked(task, now):
        return 'Hoàn thành các bài trước cùng kỹ năng để mở bài này.'
    return ''


def assert_can_submit(task):
    problem = submission_problem(task)
    if problem:
        raise ValidationError(problem)

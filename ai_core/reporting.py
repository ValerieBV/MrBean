"""Published grading data shared by reports and learner result endpoints."""
from django.urls import reverse


REPORT_STATUS_LABELS = {
    'not_submitted': 'Chưa làm',
    'in_progress': 'Đang làm · chưa nộp',
    'queued': 'Đang xử lý bài nộp',
    'processing': 'Đang xử lý bài nộp',
    'ai_reviewed': 'Chờ giáo viên chấm',
    'manual': 'Chờ giáo viên chấm',
    'graded': 'Đã xác nhận kết quả',
    'complete': 'Hoàn thành',
    'incomplete': 'Chưa hoàn thành',
    'assessed': 'Đã chấm · cần xác nhận hoàn thành',
    'exempt': 'Được miễn',
    'exemption_pending': 'Chờ duyệt miễn',
    'locked': 'Chưa mở',
    'closed': 'Đã đóng',
}


def report_job(job):
    """Use an allowlist so draft scores and model feedback stay internal."""
    published = job.status == 'graded'
    return {
        'id': job.pk,
        'task_id': job.task_id,
        'learner_id': job.task.learner_id,
        'learner_name': job.task.learner.get_full_name() or job.task.learner.username,
        'title': job.task.title,
        'kind': job.kind,
        'status': job.status,
        'status_label': job.public_status_label,
        'completion_status': job.completion_status if published else 'pending',
        'completion_label': REPORT_STATUS_LABELS.get(job.completion_status, 'Chờ xác nhận') if published else 'Chờ chấm',
        'submitted_at': job.submitted_at.isoformat(),
        'teacher_feedback': job.teacher_feedback if published else '',
        'reviewed_at': job.finished_at.isoformat() if published and job.finished_at else None,
        'detail_url': reverse('submissions:result', args=[job.pk]),
    }

"""Published grading data shared by reports and learner result endpoints."""
from django.urls import reverse


REPORT_STATUS_LABELS = {
    'not_submitted': 'Chưa nộp',
    'queued': 'Đang xử lý bài nộp',
    'processing': 'Đang xử lý bài nộp',
    'ai_reviewed': 'Chờ giáo viên chấm',
    'manual': 'Chờ giáo viên chấm',
    'graded': 'Đã có điểm cuối cùng',
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
        'status_label': REPORT_STATUS_LABELS.get(job.status, job.get_status_display()),
        'submitted_at': job.submitted_at.isoformat(),
        'final_score': job.final_score if published else None,
        'teacher_feedback': job.teacher_feedback if published else '',
        'reviewed_at': job.finished_at.isoformat() if published and job.finished_at else None,
        'detail_url': reverse('submissions:result', args=[job.pk]),
    }

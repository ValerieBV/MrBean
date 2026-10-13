from datetime import timedelta
from django.conf import settings
from django.db.models import Avg, Exists, OuterRef, Subquery, Count, Min, Max, F
from django.utils import timezone
from ai_core.models import GradingJob
from ai_core.permissions import tasks_for
from ai_core.views import serialize


def metrics_for(user, now=None):
    now = now or timezone.now()
    tasks = tasks_for(user).filter(assigned_at__lte=now)
    jobs = GradingJob.objects.filter(task__in=tasks, submitted_at__lte=now)
    assigned = tasks.count()
    submitted = tasks.annotate(has_job=Exists(jobs.filter(task_id=OuterRef('pk')))).filter(has_job=True).count()
    # Latest confirmed attempt per assignment/learner, so resubmissions do not inflate averages.
    latest_grade = jobs.filter(task_id=OuterRef('pk'), status='graded').order_by('-submitted_at', '-pk')
    final_avg = tasks.annotate(score=Subquery(latest_grade.values('final_score')[:1])).aggregate(value=Avg('score'))['value']
    latest_ai = jobs.filter(task_id=OuterRef('pk'), suggested_score__isnull=False).order_by('-submitted_at', '-pk')
    ai_avg = tasks.annotate(score=Subquery(latest_ai.values('suggested_score')[:1])).aggregate(value=Avg('score'))['value']
    latest = jobs.filter(task_id=OuterRef('pk')).order_by('-submitted_at', '-pk')
    progress_tasks = tasks.annotate(
        latest_status=Subquery(latest.values('status')[:1]),
        confirmed_score=Subquery(latest_grade.values('final_score')[:1]),
    ).select_related('learner')
    learners = {}
    for task in progress_tasks:
        row = learners.setdefault(task.learner_id, {
            'learner_id': task.learner_id, 'learner_name': task.learner.get_full_name() or task.learner.username,
            'assigned': 0, 'submitted': 0, 'not_submitted': 0, 'awaiting_grade': 0,
            'graded': 0, 'overdue_not_submitted': 0, 'resubmissions_pending': 0, '_scores': [],
        })
        row['assigned'] += 1
        if task.latest_status is None:
            row['not_submitted'] += 1
            row['overdue_not_submitted'] += int(task.due_at < now)
        else:
            row['submitted'] += 1
            row['graded' if task.latest_status == 'graded' else 'awaiting_grade'] += 1
            if task.confirmed_score is not None and task.latest_status != 'graded':
                row['resubmissions_pending'] += 1
        if task.confirmed_score is not None:
            row['_scores'].append(task.confirmed_score)
    for row in learners.values():
        scores = row.pop('_scores')
        row['average_score'] = round(sum(scores) / len(scores), 2) if scores else None
        row['submission_rate'] = round(row['submitted'] / row['assigned'] * 100, 2)
    confirmed = jobs.filter(status='graded').select_related('task__learner', 'reviewed_by')
    late = confirmed.filter(finished_at__gte=F('submitted_at') + timedelta(hours=48))
    def grade_row(job):
        item = serialize(job)
        item['learner_name'] = job.task.learner.get_full_name() or job.task.learner.username
        item['reviewed_at'] = job.finished_at.isoformat() if job.finished_at else None
        item['reviewed_by'] = job.reviewed_by.username if job.reviewed_by else None
        item['sla_breached'] = job.finished_at >= job.sla_deadline if job.finished_at else None
        item['hours_to_grade'] = round((job.finished_at - job.submitted_at).total_seconds() / 3600, 2) if job.finished_at else None
        return item
    pending = jobs.exclude(status='graded').select_related('task')
    alerts = []
    for job in pending.filter(submitted_at__lte=now - timedelta(hours=48 - settings.SLA_WARNING_HOURS)):
        item = serialize(job)
        item['flag'] = 'red' if now >= job.sla_deadline else 'yellow'
        item['remaining_hours'] = round((job.sla_deadline - now).total_seconds() / 3600, 2)
        alerts.append(item)
    # Explainable rule: at least N overdue unsubmitted tasks, OR no submission for D days
    # while at least one task is overdue. Never label a new learner without overdue work.
    missed = tasks.filter(due_at__lt=now).annotate(has_job=Exists(jobs.filter(task_id=OuterRef('pk')))).filter(has_job=False)
    counts = missed.values('learner_id').annotate(count=Count('pk'))
    last_by_learner = dict(jobs.values('task__learner_id').annotate(last=Max('submitted_at')).values_list('task__learner_id', 'last'))
    first_by_learner = dict(tasks.values('learner_id').annotate(first=Min('assigned_at')).values_list('learner_id', 'first'))
    risks = []
    for row in counts:
        last = last_by_learner.get(row['learner_id'])
        first = first_by_learner[row['learner_id']]
        inactive = (now - (last or first)).total_seconds() >= settings.DROPOUT_INACTIVE_DAYS * 86400
        if row['count'] >= settings.DROPOUT_MISSED_TASKS or inactive:
            risks.append({'learner_id': row['learner_id'], 'missed_tasks': row['count'],
                          'last_submission_at': last.isoformat() if last else None,
                          'reason': 'missed_tasks' if row['count'] >= settings.DROPOUT_MISSED_TASKS else 'inactive'})
    queue = jobs.filter(status__in=['manual', 'ai_reviewed']).select_related('task')
    return {
        'learner_progress': sorted(learners.values(), key=lambda row: row['learner_id']),
        'graded_count': confirmed.count(), 'graded_report': [grade_row(job) for job in confirmed.order_by('-finished_at', '-pk')[:100]],
        'sla_late_count': late.count(), 'sla_late_report': [grade_row(job) for job in late.order_by('-finished_at', '-pk')[:100]],
        'updated_at': now.isoformat(), 'assigned_count': assigned, 'submitted_count': submitted,
        'submission_rate': round(submitted / assigned * 100, 2) if assigned else 0,
        'average_score': round(final_avg, 2) if final_avg is not None else None,
        'average_ai_suggestion': round(ai_avg, 2) if ai_avg is not None else None,
        'status_counts': list(jobs.values('status').annotate(count=Count('pk')).order_by('status')),
        'sla_alerts': alerts, 'at_risk_learners': risks,
        'review_queue': [serialize(job) for job in queue[:100]],
        'review_queue_count': queue.count(),
    }

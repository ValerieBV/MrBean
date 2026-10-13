from datetime import timedelta
from django.conf import settings
from django.db.models import Avg, Exists, OuterRef, Subquery, Count, Min, Max
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
        'updated_at': now.isoformat(), 'assigned_count': assigned, 'submitted_count': submitted,
        'submission_rate': round(submitted / assigned * 100, 2) if assigned else 0,
        'average_score': round(final_avg, 2) if final_avg is not None else None,
        'average_ai_suggestion': round(ai_avg, 2) if ai_avg is not None else None,
        'status_counts': list(jobs.values('status').annotate(count=Count('pk')).order_by('status')),
        'sla_alerts': alerts, 'at_risk_learners': risks,
        'review_queue': [serialize(job) for job in queue[:100]],
        'review_queue_count': queue.count(),
    }

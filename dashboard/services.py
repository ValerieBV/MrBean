from datetime import timedelta
from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Avg, OuterRef, Subquery, Q
from django.utils import timezone
from django.utils.dateparse import parse_date
from ai_core.models import GradingJob
from ai_core.permissions import tasks_for, classes_for, is_manager
from ai_core.views import serialize


def paginate(rows, number, size=25):
    page = Paginator(rows, size).get_page(number)
    return page, {'page': page.number, 'pages': page.paginator.num_pages, 'total': page.paginator.count}


def filtered_tasks(user, filters, now=None):
    tasks = tasks_for(user).filter(assigned_at__lte=now or timezone.now())
    if filters.get('classroom'):
        tasks = tasks.filter(assignment__classroom_id=filters['classroom'])
    if filters.get('skill') in ('listening', 'speaking', 'vocabulary'):
        tasks = tasks.filter(assignment__lesson__skill=filters['skill'])
    for key, lookup in [('date_from','assigned_at__date__gte'),('date_to','assigned_at__date__lte')]:
        if filters.get(key):
            date = parse_date(filters[key])
            if date is None:
                raise ValueError('invalid_date')
            tasks = tasks.filter(**{lookup:date})
    if filters.get('q'):
        q = filters['q'][:100]
        tasks = tasks.filter(Q(title__icontains=q) | Q(learner__username__icontains=q) |
                             Q(learner__first_name__icontains=q) | Q(learner__last_name__icontains=q))
    return tasks


def metrics_for(user, now=None, filters=None):
    now, filters = now or timezone.now(), filters or {}
    tasks = filtered_tasks(user, filters, now)
    jobs = GradingJob.objects.filter(task__in=tasks, submitted_at__lte=now)
    latest = jobs.filter(task_id=OuterRef('pk')).order_by('-submitted_at', '-pk')
    latest_grade = latest.filter(status='graded')
    latest_ai = latest.filter(suggested_score__isnull=False)
    data_tasks = tasks.annotate(
        latest_status=Subquery(latest.values('status')[:1]),
        latest_at=Subquery(latest.values('submitted_at')[:1]),
        confirmed_score=Subquery(latest_grade.values('final_score')[:1]),
        ai_score=Subquery(latest_ai.values('suggested_score')[:1]),
    ).select_related('learner', 'assignment__classroom', 'assignment__lesson').order_by('learner__username', 'pk')
    totals = data_tasks.aggregate(average_score=Avg('confirmed_score'), average_ai_suggestion=Avg('ai_score'))
    assigned = submitted = 0
    learners = {}
    for task in data_tasks:
        assigned += 1
        done = task.latest_status is not None
        submitted += int(done)
        row = learners.setdefault(task.learner_id, dict(learner_id=task.learner_id,
            learner_name=task.learner.get_full_name() or task.learner.username,
            student_code=task.learner.student_code or '', assigned=0, submitted=0, not_submitted=0,
            awaiting_grade=0, graded=0, overdue_not_submitted=0, resubmissions_pending=0,
            _scores=[], _first=task.assigned_at, _last=None))
        row['assigned'] += 1
        row['_first'] = min(row['_first'], task.assigned_at)
        if done:
            row['submitted'] += 1
            row['graded' if task.latest_status == 'graded' else 'awaiting_grade'] += 1
            row['_last'] = max(row['_last'] or task.latest_at, task.latest_at)
            if task.confirmed_score is not None and task.latest_status != 'graded':
                row['resubmissions_pending'] += 1
        else:
            row['not_submitted'] += 1
            row['overdue_not_submitted'] += int(task.due_at < now)
        if task.confirmed_score is not None:
            row['_scores'].append(task.confirmed_score)
    risks = []
    for row in learners.values():
        scores = row.pop('_scores')
        row['average_score'] = round(sum(scores)/len(scores), 2) if scores else None
        row['submission_rate'] = round(row['submitted']/row['assigned']*100, 2)
        first, last = row.pop('_first'), row.pop('_last')
        inactive = now - (last or first) >= timedelta(days=settings.DROPOUT_INACTIVE_DAYS)
        if row['overdue_not_submitted'] >= settings.DROPOUT_MISSED_TASKS or (row['overdue_not_submitted'] and inactive):
            risks.append(dict(learner_id=row['learner_id'], learner_name=row['learner_name'],
                missed_tasks=row['overdue_not_submitted'], last_submission_at=last.isoformat() if last else None,
                reason='missed_tasks' if row['overdue_not_submitted'] >= settings.DROPOUT_MISSED_TASKS else 'inactive'))
    progress_page, progress_meta = paginate(list(learners.values()), filters.get('progress_page'))
    task_page, task_meta = paginate(data_tasks, filters.get('tasks_page'))
    task_rows = [dict(id=t.pk, title=t.title, learner_name=t.learner.get_full_name() or t.learner.username,
        classroom=t.assignment.classroom.class_code if t.assignment_id else 'Cũ',
        skill=t.assignment.rubric.get('skill', '') if t.assignment_id else '',
        due_at=t.due_at.isoformat(), latest_status=t.latest_status or 'not_submitted',
        final_score=t.confirmed_score, suggested_score=t.ai_score,
        submit_url=f'/hoc-tap/tasks/{t.pk}/' if t.assignment_id else None) for t in task_page]
    confirmed = jobs.filter(status='graded').select_related('task__learner').order_by('-submitted_at', '-pk')
    graded_page, grade_meta = paginate(confirmed, filters.get('grades_page'))
    history_page, history_meta = paginate(jobs.select_related('task__learner').order_by('-submitted_at', '-pk'), filters.get('history_page'))
    pending = jobs.filter(status__in=['manual', 'ai_reviewed']).select_related('task__learner')
    queue_page, queue_meta = paginate(pending, filters.get('queue_page'))
    staff = is_manager(user) or user.role == 'teacher'
    return {
        'role': 'manager' if is_manager(user) else user.role,
        'updated_at': now.isoformat(), 'assigned_count': assigned, 'submitted_count': submitted,
        'submission_rate': round(submitted/assigned*100, 2) if assigned else 0,
        **{k: round(v, 2) if v is not None else None for k, v in totals.items()},
        'class_count': classes_for(user).count(), 'learner_count': len(learners),
        'learner_progress': list(progress_page), 'progress_pagination': progress_meta,
        'tasks': task_rows, 'tasks_pagination': task_meta,
        'graded_report': [serialize(j) for j in graded_page], 'graded_count': grade_meta['total'], 'grades_pagination': grade_meta,
        'history': [serialize(j) for j in history_page], 'history_pagination': history_meta,
        'review_queue': [serialize(j) for j in queue_page] if staff else [],
        'review_queue_count': queue_meta['total'] if staff else 0, 'queue_pagination': queue_meta,
        'at_risk_learners': risks,
    }

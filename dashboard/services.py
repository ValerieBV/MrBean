from datetime import timedelta
from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Avg, OuterRef, Subquery, Q, Exists
from django.utils import timezone
from django.utils.dateparse import parse_date
from ai_core.models import GradingJob
from ai_core.permissions import tasks_for, classes_for, is_manager
from ai_core.views import serialize
from courses.models import Enrollment, ExemptionRequest
from .models import LearningTask


def paginate(rows, number, size=25):
    page = Paginator(rows, size).get_page(number)
    return page, {'page':page.number, 'pages':page.paginator.num_pages, 'total':page.paginator.count}


def filtered_tasks(user, filters, now=None):
    now = now or timezone.now()
    tasks = tasks_for(user).filter(assigned_at__lte=now).annotate(current_enrollment=Exists(
        Enrollment.objects.filter(student_id=OuterRef('learner_id'), classroom_id=OuterRef('assignment__classroom_id'), status='active')))
    if filters.get('scope') != 'all':
        tasks = tasks.filter(learner__is_active=True).filter(Q(assignment__isnull=True) |
            Q(assignment__is_active=True, assignment__classroom__is_active=True, current_enrollment=True))
    if filters.get('classroom'):
        tasks = tasks.filter(assignment__classroom_id=int(filters['classroom']))
    if filters.get('skill') in ('listening','speaking','vocabulary'):
        tasks = tasks.filter(assignment__lesson__skill=filters['skill'])
    for key, lookup in [('date_from','assigned_at__date__gte'), ('date_to','assigned_at__date__lte')]:
        if filters.get(key):
            date = parse_date(filters[key])
            if date is None: raise ValueError('invalid_date')
            tasks = tasks.filter(**{lookup:date})
    if filters.get('date_from') and filters.get('date_to') and filters['date_from'] > filters['date_to']:
        raise ValueError('invalid_date_range')
    if filters.get('q'):
        q = filters['q'][:100]
        tasks = tasks.filter(Q(title__icontains=q) | Q(learner__username__icontains=q) |
            Q(learner__first_name__icontains=q) | Q(learner__last_name__icontains=q))
    return tasks


def annotated_tasks(user, filters=None, now=None):
    now = now or timezone.now()
    tasks = filtered_tasks(user, filters or {}, now)
    latest = GradingJob.objects.filter(task_id=OuterRef('pk'), submitted_at__lte=now).order_by('-submitted_at','-pk')
    grade = latest.filter(status='graded')
    ai = latest.filter(suggested_score__isnull=False)
    earlier = LearningTask.objects.filter(learner_id=OuterRef('learner_id'),
        assignment__classroom_id=OuterRef('assignment__classroom_id'), assignment__is_active=True,
        assignment__lesson__skill=OuterRef('assignment__lesson__skill'), assignment__lesson__program=OuterRef('assignment__lesson__program'),
        assignment__lesson__order__lt=OuterRef('assignment__lesson__order'), assigned_at__lte=now,
        exemption__isnull=True, jobs__isnull=True)
    return tasks.annotate(latest_status=Subquery(latest.values('status')[:1]),
        latest_job_id=Subquery(latest.values('pk')[:1]), latest_at=Subquery(latest.values('submitted_at')[:1]),
        confirmed_score=Subquery(grade.values('final_score')[:1]), confirmed_job_id=Subquery(grade.values('pk')[:1]),
        ai_score=Subquery(ai.values('suggested_score')[:1]), earlier_unfinished=Exists(earlier),
        pending_exemption_id=Subquery(ExemptionRequest.objects.filter(assignment_id=OuterRef('assignment_id'),
            enrollment__student_id=OuterRef('learner_id'), status='pending').values('pk')[:1])).select_related(
        'learner', 'assignment__classroom', 'assignment__lesson', 'exemption').order_by('learner__username','pk')


def task_state(task, now):
    if task.exemption_id: return 'exempt', 'Đã được miễn bài này.'
    if task.pending_exemption_id: return 'exemption_pending', 'Đơn miễn đang chờ duyệt.'
    if task.assignment_id:
        if not task.assignment.is_active or not task.assignment.classroom.is_active or not task.current_enrollment or not task.learner.is_active:
            return task.latest_status or 'closed', 'Bài hoặc ghi danh đã ngừng hoạt động.'
        if task.assignment.requires_previous and task.earlier_unfinished:
            return task.latest_status or 'locked', 'Hoàn thành bài trước cùng kỹ năng.'
        if task.due_at < now and not task.assignment.allow_late_submission:
            return task.latest_status or 'closed', 'Bài đã đóng nhận nộp muộn.'
    return task.latest_status or 'not_submitted', ''


def metrics_for(user, now=None, filters=None):
    now, filters = now or timezone.now(), filters or {}
    tasks = annotated_tasks(user, filters, now)
    eligible = tasks.filter(exemption__isnull=True)
    totals = eligible.aggregate(average_score=Avg('confirmed_score'), average_ai_suggestion=Avg('ai_score'))
    all_tasks = list(tasks)
    assigned = submitted = exempt = pending_exemptions = 0
    learners = {}
    task_rows = []
    for task in all_tasks:
        state, blocked = task_state(task, now)
        done = task.latest_status is not None
        excused = bool(task.exemption_id)
        assigned += int(not excused); submitted += int(done and not excused); exempt += int(excused)
        pending_exemptions += int(bool(task.pending_exemption_id))
        row = learners.setdefault(task.learner_id, dict(learner_id=task.learner_id,
            learner_name=task.learner.get_full_name() or task.learner.username, student_code=task.learner.student_code or '',
            assigned=0, submitted=0, exempt=0, not_submitted=0, awaiting_grade=0, graded=0,
            overdue_not_submitted=0, resubmissions_pending=0, _scores=[], _first=task.assigned_at, _last=None))
        row['_first'] = min(row['_first'], task.assigned_at)
        if excused: row['exempt'] += 1
        else:
            row['assigned'] += 1
            if done:
                row['submitted'] += 1
                row['graded' if task.latest_status=='graded' else 'awaiting_grade'] += 1
                row['_last'] = max(row['_last'] or task.latest_at, task.latest_at)
                if task.confirmed_score is not None and task.latest_status!='graded': row['resubmissions_pending'] += 1
            else:
                row['not_submitted'] += 1
                live = task.learner.is_active and (not task.assignment_id or
                    (task.assignment.is_active and task.assignment.classroom.is_active and task.current_enrollment))
                # A locked lesson or a pending request is not treated as learner inactivity.
                risk_eligible = live and not task.pending_exemption_id and not (task.assignment_id and task.assignment.requires_previous and task.earlier_unfinished)
                row['overdue_not_submitted'] += int(task.due_at < now and risk_eligible)
            if task.confirmed_score is not None: row['_scores'].append(task.confirmed_score)
        task_rows.append(dict(id=task.pk, title=task.title, learner_name=row['learner_name'],
            classroom=task.assignment.classroom.class_code if task.assignment_id else 'Bài cũ',
            skill=task.assignment.rubric.get('skill','') if task.assignment_id else '', due_at=task.due_at.isoformat(),
            latest_status=state, final_score=task.confirmed_score, suggested_score=task.ai_score,
            is_late=task.due_at < now and not done and not excused, blocked_reason=blocked,
            submit_url=f'/hoc-tap/tasks/{task.pk}/' if task.assignment_id else None,
            result_url=f'/hoc-tap/results/{task.latest_job_id}/' if task.latest_job_id else None))
    risks = []
    for row in learners.values():
        scores = row.pop('_scores')
        row['average_score'] = round(sum(scores)/len(scores),2) if scores else None
        row['submission_rate'] = round(row['submitted']/row['assigned']*100,2) if row['assigned'] else 0
        first, last = row.pop('_first'), row.pop('_last')
        inactive = now - (last or first) >= timedelta(days=settings.DROPOUT_INACTIVE_DAYS)
        if row['overdue_not_submitted'] >= settings.DROPOUT_MISSED_TASKS or (row['overdue_not_submitted'] and inactive):
            risks.append(dict(learner_id=row['learner_id'], learner_name=row['learner_name'],
                missed_tasks=row['overdue_not_submitted'], last_submission_at=last.isoformat() if last else None,
                reason='missed_tasks' if row['overdue_not_submitted'] >= settings.DROPOUT_MISSED_TASKS else 'inactive'))
    jobs = GradingJob.objects.filter(task__in=tasks, submitted_at__lte=now).select_related('task__learner')
    progress_page, progress_meta = paginate(list(learners.values()), filters.get('progress_page'))
    task_page, task_meta = paginate(task_rows, filters.get('tasks_page'))
    graded_page, grade_meta = paginate(jobs.filter(status='graded').order_by('-submitted_at','-pk'), filters.get('grades_page'))
    history_page, history_meta = paginate(jobs.order_by('-submitted_at','-pk'), filters.get('history_page'))
    queue_page, queue_meta = paginate(jobs.filter(status__in=['manual','ai_reviewed']).order_by('submitted_at','pk'), filters.get('queue_page'))
    staff = is_manager(user) or user.role=='teacher'
    return {'role':'manager' if is_manager(user) else user.role, 'updated_at':now.isoformat(),
        'assigned_count':assigned, 'submitted_count':submitted, 'exempt_count':exempt, 'exemption_pending_count':pending_exemptions,
        'submission_rate':round(submitted/assigned*100,2) if assigned else 0,
        **{k:round(v,2) if v is not None else None for k,v in totals.items()},
        'class_count':classes_for(user).count(), 'learner_count':len(learners),
        'learner_progress':list(progress_page), 'progress_pagination':progress_meta,
        'tasks':list(task_page), 'tasks_pagination':task_meta,
        'graded_report':[serialize(j) for j in graded_page], 'graded_count':grade_meta['total'], 'grades_pagination':grade_meta,
        'history':[serialize(j) for j in history_page], 'history_pagination':history_meta,
        'review_queue':[serialize(j) for j in queue_page] if staff else [],
        'review_queue_count':queue_meta['total'] if staff else 0, 'queue_pagination':queue_meta,
        'at_risk_learners':risks}

from datetime import timedelta
from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import OuterRef, Subquery, Q, Exists
from django.utils import timezone
from django.utils.dateparse import parse_date
from ai_core.models import GradingJob
from ai_core.permissions import tasks_for, classes_for, is_manager
from ai_core.reporting import report_job, REPORT_STATUS_LABELS
from ai_core.diagnostics import review_status_label
from courses.models import Enrollment, ExemptionRequest
from .models import LearningTask
from submissions.models import LessonProgress
from submissions.progress import unfinished_tasks


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
    earlier = LearningTask.objects.filter(learner_id=OuterRef('learner_id'),
        assignment__classroom_id=OuterRef('assignment__classroom_id'), assignment__is_active=True,
        assignment__lesson__skill=OuterRef('assignment__lesson__skill'), assignment__lesson__program=OuterRef('assignment__lesson__program'),
        assignment__lesson__order__lt=OuterRef('assignment__lesson__order'), assigned_at__lte=now,
        exemption__isnull=True)
    earlier = unfinished_tasks(earlier, now)
    return tasks.annotate(latest_status=Subquery(latest.values('status')[:1]),
        latest_job_id=Subquery(latest.values('pk')[:1]), latest_at=Subquery(latest.values('submitted_at')[:1]),
        confirmed_feedback=Subquery(grade.values('teacher_feedback')[:1]), confirmed_job_id=Subquery(grade.values('pk')[:1]),
        confirmed_completion=Subquery(grade.values('completion_status')[:1]),
        confirmed_submission_at=Subquery(grade.values('submitted_at')[:1]),
        has_draft=Exists(LessonProgress.objects.filter(student_id=OuterRef('learner_id'),
            lesson_id=OuterRef('assignment__lesson_id'), draft_saved_at__gte=now-timedelta(hours=24)).exclude(draft={})),
        earlier_unfinished=Exists(earlier),
        pending_exemption_id=Subquery(ExemptionRequest.objects.filter(assignment_id=OuterRef('assignment_id'),
            enrollment__student_id=OuterRef('learner_id'), status='pending').values('pk')[:1])).select_related(
        'learner', 'assignment__classroom', 'assignment__lesson', 'exemption').order_by('learner__username','pk')


def task_state(task, now):
    state = {'complete': 'complete', 'incomplete': 'incomplete', 'pending': 'assessed'}.get(
        task.confirmed_completion, task.latest_status or ('in_progress' if task.has_draft else 'not_submitted'))
    if task.exemption_id: return 'exempt', 'Đã được miễn bài này.'
    if task.pending_exemption_id: return 'exemption_pending', 'Đơn miễn đang chờ duyệt.'
    if task.assignment_id:
        if not task.assignment.is_active or not task.assignment.classroom.is_active or not task.current_enrollment or not task.learner.is_active:
            return state if task.latest_status else 'closed', 'Bài hoặc ghi danh đã ngừng hoạt động.'
        if task.assignment.requires_previous and task.earlier_unfinished:
            return state if task.latest_status else 'locked', 'Cần được xác nhận hoàn thành bài trước cùng kỹ năng.'
        if task.due_at < now and not task.assignment.allow_late_submission:
            return state if task.latest_status else 'closed', 'Bài đã đóng nhận nộp muộn.'
    return state, ''


def metrics_for(user, now=None, filters=None):
    now, filters = now or timezone.now(), filters or {}
    tasks = annotated_tasks(user, filters, now)
    all_tasks = list(tasks)
    assigned = submitted = completed = incomplete = on_time = exempt = pending_exemptions = 0
    learners = {}
    task_rows = []
    for task in all_tasks:
        state, blocked = task_state(task, now)
        done = task.latest_status is not None
        excused = bool(task.exemption_id)
        complete = task.confirmed_completion == 'complete' and not excused
        missing = task.confirmed_completion == 'incomplete' and not excused
        completed += int(complete)
        incomplete += int(missing)
        completed_in_time = complete and task.confirmed_submission_at <= task.due_at
        on_time += int(completed_in_time)
        assigned += int(not excused); submitted += int(done and not excused); exempt += int(excused)
        pending_exemptions += int(bool(task.pending_exemption_id))
        row = learners.setdefault(task.learner_id, dict(learner_id=task.learner_id,
            learner_name=task.learner.get_full_name() or task.learner.username, student_code=task.learner.student_code or '',
            assigned=0, submitted=0, exempt=0, not_submitted=0, awaiting_grade=0, graded=0,
            completed=0, incomplete=0, in_progress=0, on_time_completed=0, completion_pending=0,
            overdue_not_submitted=0, overdue_incomplete=0, resubmissions_pending=0, _first=task.assigned_at, _last=None))
        row['_first'] = min(row['_first'], task.assigned_at)
        if excused: row['exempt'] += 1
        else:
            row['assigned'] += 1
            row['completed'] += int(complete)
            row['incomplete'] += int(missing)
            row['on_time_completed'] += int(completed_in_time)
            row['completion_pending'] += int(task.confirmed_completion == 'pending')
            if done:
                row['submitted'] += 1
                row['graded' if task.latest_status=='graded' else 'awaiting_grade'] += 1
                row['_last'] = max(row['_last'] or task.latest_at, task.latest_at)
                if task.confirmed_job_id is not None and task.latest_status!='graded': row['resubmissions_pending'] += 1
            else:
                row['not_submitted'] += int(not task.has_draft)
                row['in_progress'] += int(task.has_draft)
            live = task.learner.is_active and (not task.assignment_id or
                (task.assignment.is_active and task.assignment.classroom.is_active and task.current_enrollment))
            risk_eligible = live and not task.pending_exemption_id and not (task.assignment_id and task.assignment.requires_previous and task.earlier_unfinished)
            row['overdue_not_submitted'] += int(not done and task.due_at < now and risk_eligible)
            # Pending teacher/AI review is not learner inactivity.
            row['overdue_incomplete'] += int(missing and task.latest_status == 'graded' and task.due_at < now and risk_eligible)
        task_rows.append(dict(id=task.pk, title=task.title, learner_name=row['learner_name'],
            classroom=task.assignment.classroom.class_code if task.assignment_id else 'Bài cũ',
            skill=task.assignment.rubric.get('skill','') if task.assignment_id else '', due_at=task.due_at.isoformat(),
            latest_status=state,
            completion_status=task.confirmed_completion or 'pending',
            completion_label=REPORT_STATUS_LABELS.get(state,state), completed_on_time=bool(completed_in_time),
            processing_status=task.latest_status, resubmission_pending=bool(task.latest_status in ('queued','processing','ai_reviewed','manual') and task.confirmed_job_id),
            is_late=task.due_at < now and not complete and not excused, blocked_reason=blocked,
            submit_url=f'/hoc-tap/tasks/{task.pk}/' if task.assignment_id else None,
            result_url=f'/hoc-tap/results/{task.latest_job_id}/' if task.latest_job_id else None))
    risks = []
    for row in learners.values():
        row['submission_rate'] = round(row['submitted']/row['assigned']*100,2) if row['assigned'] else 0
        row['completion_rate'] = round(row['completed']/row['assigned']*100,2) if row['assigned'] else 0
        first, last = row.pop('_first'), row.pop('_last')
        inactive = now - (last or first) >= timedelta(days=settings.DROPOUT_INACTIVE_DAYS)
        overdue = row['overdue_not_submitted'] + row['overdue_incomplete']
        if overdue >= settings.DROPOUT_MISSED_TASKS or (overdue and inactive):
            risks.append(dict(learner_id=row['learner_id'], learner_name=row['learner_name'],
                missed_tasks=overdue, incomplete_tasks=row['overdue_incomplete'], last_submission_at=last.isoformat() if last else None,
                reason='missed_tasks' if overdue >= settings.DROPOUT_MISSED_TASKS else 'inactive'))
    jobs = GradingJob.objects.filter(task__in=tasks, submitted_at__lte=now).select_related('task__learner')
    progress_page, progress_meta = paginate(list(learners.values()), filters.get('progress_page'))
    task_page, task_meta = paginate(task_rows, filters.get('tasks_page'))
    graded_page, grade_meta = paginate(jobs.filter(status='graded').order_by('-submitted_at','-pk'), filters.get('grades_page'))
    history_page, history_meta = paginate(jobs.order_by('-submitted_at','-pk'), filters.get('history_page'))
    queue_page, queue_meta = paginate(jobs.filter(Q(status__in=['manual','ai_reviewed']) |
        Q(status='graded', completion_status='pending')).order_by('submitted_at','pk'), filters.get('queue_page'))
    staff = is_manager(user) or user.role=='teacher'
    return {'role':'manager' if is_manager(user) else user.role, 'updated_at':now.isoformat(),
        'assigned_count':assigned, 'submitted_count':submitted, 'exempt_count':exempt, 'exemption_pending_count':pending_exemptions,
        'submission_rate':round(submitted/assigned*100,2) if assigned else 0,
        'completed_count':completed, 'incomplete_count':incomplete, 'on_time_completed_count':on_time,
        'completion_rate':round(completed/assigned*100,2) if assigned else 0,
        'class_count':classes_for(user).count(), 'learner_count':len(learners),
        'learner_progress':list(progress_page), 'progress_pagination':progress_meta,
        'tasks':list(task_page), 'tasks_pagination':task_meta,
        'graded_report':[report_job(j) for j in graded_page], 'graded_count':grade_meta['total'], 'grades_pagination':grade_meta,
        'history':[report_job(j) for j in history_page], 'history_pagination':history_meta,
        'review_queue':[dict(report_job(j), review_status_label=review_status_label(j)) for j in queue_page] if staff else [],
        'review_queue_count':queue_meta['total'] if staff else 0, 'queue_pagination':queue_meta,
        'at_risk_learners':risks}

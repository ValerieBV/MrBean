from datetime import timedelta
from django.contrib.auth import get_user_model
from django.db.models import OuterRef, Subquery, Q, Exists, Case, When, Value, BooleanField
from django.utils import timezone
from django.utils.dateparse import parse_date
from ai_core.models import GradingJob
from ai_core.permissions import tasks_for, classes_for, is_manager
from courses.models import Enrollment, ExemptionRequest
from .models import LearningTask
from submissions.progress import unfinished_tasks


def learner_classes(user):
    from courses.models import ClassRoom
    return ClassRoom.objects.filter(Q(enrollments__student=user) | Q(assignments__tasks__learner=user)).distinct()


def class_options(user):
    if not is_manager(user) and user.role == 'student':
        return learner_classes(user)
    return classes_for(user)


def roster(user, *, historical=False, classroom='', now=None):
    """Enrollment includes students with no tasks; legacy visibility still follows tasks_for."""
    people = get_user_model().objects.all()
    if is_manager(user) and not classroom:
        records = filtered_tasks(user, {'scope': 'all' if historical else 'live'}, now)
        people = people.filter(Q(role='student') | Q(pk__in=records.values('learner_id')))
        return people if historical else people.filter(is_active=True)
    if not is_manager(user) and user.role == 'student':
        people = people.filter(pk=user.pk)
    memberships = Enrollment.objects.filter(classroom__in=class_options(user))
    if not historical:
        memberships = memberships.filter(status='active', classroom__is_active=True, student__is_active=True)
    tasks = filtered_tasks(user, {'classroom': classroom, 'scope': 'all' if historical else 'live'}, now)
    if classroom == 'legacy':
        memberships = memberships.none()
    elif classroom:
        memberships = memberships.filter(classroom_id=int(classroom))
    return people.filter(Q(pk__in=memberships.values('student_id')) | Q(pk__in=tasks.values('learner_id')))


def code_search(q):
    lookup = Q(student_code__icontains=q)
    ref = q.upper().rsplit(' · ', 1)[-1]
    has_ref = ref.startswith('HV#')
    ref = ref.removeprefix('HV#')
    if has_ref and ref.isascii() and ref.isdigit() and len(ref) <= 18:
        lookup |= Q(pk=int(ref))
    return lookup


def student_label(pk, code, duplicates=()):
    code = (code or '').strip()
    if not code:
        return f'HV#{pk}'
    return f'{code} · HV#{pk}' if code.casefold() in duplicates else code


def filtered_tasks(user, filters, now=None):
    now = now or timezone.now()
    tasks = tasks_for(user).filter(assigned_at__lte=now).annotate(current_enrollment=Exists(
        Enrollment.objects.filter(student_id=OuterRef('learner_id'), classroom_id=OuterRef('assignment__classroom_id'), status='active')))
    if filters.get('scope') != 'all':
        tasks = tasks.filter(learner__is_active=True).filter(Q(assignment__isnull=True) |
            Q(assignment__is_active=True, assignment__classroom__is_active=True, current_enrollment=True))
    if classroom := filters.get('classroom'):
        tasks = tasks.filter(assignment__isnull=True) if classroom == 'legacy' else tasks.filter(assignment__classroom_id=int(classroom))
    if filters.get('skill') == 'legacy':
        tasks = tasks.filter(assignment__isnull=True)
    elif filters.get('skill'):
        tasks = tasks.filter(assignment__lesson__skill=filters['skill'])
    for key, lookup in [('date_from','assigned_at__date__gte'), ('date_to','assigned_at__date__lte')]:
        if filters.get(key):
            tasks = tasks.filter(**{lookup:parse_date(filters[key])})
    if filters.get('week'):
        start = parse_date(filters['week'])
        tasks = tasks.filter(assigned_at__date__range=(start, start + timedelta(days=6)))
    if q := filters.get('q', '').strip()[:100]:
        by_code = code_search(q)
        tasks = tasks.filter(Q(title__icontains=q) | Q(learner__in=get_user_model().objects.filter(by_code)))
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
        has_draft=Case(When(Q(assignment__lesson__skill='listening', draft_saved_at__gte=now-timedelta(hours=24)) & ~Q(draft={}),
                           then=Value(True)), default=Value(False), output_field=BooleanField()),
        earlier_unfinished=Exists(earlier),
        pending_exemption_id=Subquery(ExemptionRequest.objects.filter(assignment_id=OuterRef('assignment_id'),
            enrollment__student_id=OuterRef('learner_id'), status='pending').values('pk')[:1])).select_related(
        'learner', 'assignment__classroom', 'assignment__lesson').defer(
        'assignment__rubric', 'draft').order_by('pk')


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

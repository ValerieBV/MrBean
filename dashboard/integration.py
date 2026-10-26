"""Connect real A/B models to the reporting roster, without cross-branch writes."""
from datetime import datetime
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from .models import LearningTask


def sync_assignment_roster(*, assignment_key, title, teacher, learners, assigned_at, due_at):
    if not isinstance(assignment_key, str) or not assignment_key.strip() or len(assignment_key) > 128:
        raise ValidationError('Invalid assignment key')
    if not title or len(title) > 200 or teacher.role != 'teacher':
        raise ValidationError('Invalid title or teacher')
    if not all(isinstance(v, datetime) and timezone.is_aware(v) for v in (assigned_at, due_at)) or due_at < assigned_at:
        raise ValidationError('Invalid assignment dates')
    learners = list(learners)
    if any(not learner.pk or learner.role != 'student' for learner in learners):
        raise ValidationError('Student roster required')
    rows = []
    with transaction.atomic():
        for learner in {learner.pk: learner for learner in learners}.values():
            task, created = LearningTask.objects.get_or_create(
                assignment_key=assignment_key, learner=learner,
                defaults=dict(title=title, teacher=teacher, assigned_at=assigned_at, due_at=due_at))
            if not created:
                task = LearningTask.objects.select_for_update().get(pk=task.pk)
                if task.teacher_id != teacher.pk and task.jobs.exists():
                    raise ValidationError('Cannot reassign a legacy task with submissions')
                task.title, task.teacher, task.assigned_at, task.due_at = title, teacher, assigned_at, due_at
                task.save()
            rows.append(task)
    return rows


@transaction.atomic
def sync_class_assignment(assignment):
    from courses.models import Enrollment
    teacher = assignment.classroom.teacher
    if not teacher or teacher.role != 'teacher':
        raise ValidationError('Lớp cần có giáo viên trước khi giao bài.')
    rows = []
    for enrollment in Enrollment.objects.filter(classroom=assignment.classroom, status='active').select_related('student'):
        task, created = LearningTask.objects.get_or_create(
            assignment_key=f'class-assignment:{assignment.pk}', learner=enrollment.student,
            defaults=dict(assignment=assignment, title=assignment.lesson.title, teacher=teacher,
                          assigned_at=assignment.assigned_at, due_at=assignment.due_at))
        if task.assignment_id != assignment.pk:
            raise ValidationError('Roster conflict')
        # Current class teacher is authoritative; historical grade retains reviewed_by.
        if task.teacher_id != teacher.pk:
            task.teacher = teacher
            task.save(update_fields=['teacher'])
        if created:
            from accounts.notifications import notify
            from django.urls import reverse
            notify(recipient=enrollment.student, sender=assignment.created_by,
                title='Bài tập mới: '+assignment.lesson.title,
                message='Lớp '+assignment.classroom.class_code+'. Hạn nộp: '+timezone.localtime(assignment.due_at).strftime('%d/%m/%Y %H:%M'),
                target_url=reverse('submissions:do_task',args=[task.pk]), event_key=f'assignment:{task.pk}')
        rows.append(task)
    return rows

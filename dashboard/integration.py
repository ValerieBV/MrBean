"""Server-side bridge for Member B's assignment roster (D4)."""
from datetime import datetime
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from .models import LearningTask


def sync_assignment_roster(*, assignment_key, title, teacher, learners, assigned_at, due_at):
    """Upsert every assigned learner, including those who have not submitted.

    Does not delete omitted learners or reassign historical submissions.
    Call from B's assignment transaction; learner list represents all recipients.
    """
    if not isinstance(assignment_key, str) or not assignment_key.strip() or len(assignment_key) > 128:
        raise ValidationError('Invalid assignment key')
    if not isinstance(title, str) or not title.strip() or len(title) > 200:
        raise ValidationError('Invalid title')
    if teacher.role != 'teacher' or not teacher.pk:
        raise ValidationError('Teacher required')
    if not all(isinstance(value, datetime) and timezone.is_aware(value) for value in (assigned_at, due_at)) or due_at < assigned_at:
        raise ValidationError('Invalid assignment dates')
    learners = list(learners)
    if any(not learner.pk or learner.role != 'student' for learner in learners):
        raise ValidationError('Student roster required')
    tasks = []
    with transaction.atomic():
        for learner in {learner.pk: learner for learner in learners}.values():
            task, created = LearningTask.objects.get_or_create(
                assignment_key=assignment_key, learner=learner,
                defaults={'title': title, 'teacher': teacher, 'assigned_at': assigned_at, 'due_at': due_at},
            )
            if not created:
                task = LearningTask.objects.select_for_update().get(pk=task.pk)
                if task.teacher_id != teacher.pk and task.jobs.exists():
                    raise ValidationError('Cannot reassign a task with submissions')
                task.title, task.teacher = title, teacher
                task.assigned_at, task.due_at = assigned_at, due_at
                task.save(update_fields=['title', 'teacher', 'assigned_at', 'due_at'])
            tasks.append(task)
    return tasks

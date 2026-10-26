from django.conf import settings
from django.db import models
from django.utils import timezone


class LearningTask(models.Model):
    """Assignment roster snapshot; Member B syncs one row per assigned learner."""
    assignment = models.ForeignKey('assignments.ClassAssignment', on_delete=models.PROTECT, related_name='tasks', null=True, blank=True)
    assignment_key = models.CharField(max_length=128)
    title = models.CharField(max_length=200)
    learner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='learning_tasks')
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='teaching_tasks')
    assigned_at = models.DateTimeField(default=timezone.now)
    due_at = models.DateTimeField()
    exemption = models.OneToOneField('courses.ExemptionRequest', on_delete=models.PROTECT, null=True, blank=True, related_name='exempt_task')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['assignment_key', 'learner'], name='unique_assignment_learner')]

    def __str__(self):
        return f'{self.title} / {self.learner_id}'

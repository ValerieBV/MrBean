"""Completion is an assessment, never an alias for submission or a score of 10."""
from django.db.models import OuterRef, Subquery, Q
from django.db import transaction
from django.utils import timezone
from ai_core.models import GradingJob
from .models import LessonProgress


def unfinished_tasks(queryset, now=None):
    now = now or timezone.now()
    final = GradingJob.objects.filter(task_id=OuterRef('pk'), status='graded',
        submitted_at__lte=now).order_by('-submitted_at', '-pk')
    return queryset.annotate(_confirmed_completion=Subquery(final.values('completion_status')[:1])).filter(
        Q(_confirmed_completion__isnull=True) | Q(_confirmed_completion__in=['pending', 'incomplete']))


@transaction.atomic
def sync_progress(job, *, clear_draft=False):
    """Project the most recent *graded attempt*; pending resubmits keep its result."""
    if clear_draft:
        from dashboard.models import LearningTask
        LearningTask.objects.filter(pk=job.task_id).update(draft={}, draft_saved_at=None)
    if not job.progress_id:
        return
    progress = LessonProgress.objects.select_for_update().get(pk=job.progress_id)
    newest = GradingJob.objects.filter(progress_id=job.progress_id).order_by('-submitted_at', '-pk').first()
    if newest and newest.task_id != job.task_id:
        return
    final = GradingJob.objects.filter(task_id=job.task_id, status='graded').order_by('-submitted_at', '-pk').first()
    if final:
        progress.score = final.final_score * 10 if final.final_score is not None else None
        progress.status = {'complete': 'completed', 'incomplete': 'incomplete'}.get(final.completion_status, 'assessed')
        progress.completed_at = final.submitted_at if final.completion_status == 'complete' else None
    else:
        progress.status, progress.completed_at = 'submitted', None
    fields = ['score', 'status', 'completed_at']
    progress.save(update_fields=fields)
    job.progress = progress

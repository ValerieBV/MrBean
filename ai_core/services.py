import logging
from datetime import timedelta
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from .models import GradingJob
from .providers import OpenAIGrader, validate_result

logger = logging.getLogger(__name__)


def enqueue_submission(*, task, submission_key, kind, text='', audio=None, reference_text=''):
    """Call in B's submission transaction. Same submission_key is idempotent."""
    if not isinstance(submission_key, str) or not submission_key.strip() or len(submission_key) > 128:
        raise ValidationError('Invalid submission_key')
    if kind not in ('speaking', 'vocabulary'):
        raise ValidationError('Invalid kind')
    if not isinstance(text, str) or not isinstance(reference_text, str) or max(len(text), len(reference_text)) > 20000:
        raise ValidationError('Invalid text')
    if kind == 'vocabulary' and not text.strip():
        raise ValidationError('Vocabulary text required')
    with transaction.atomic():
        type(task).objects.select_for_update().get(pk=task.pk)
        existing = GradingJob.objects.filter(submission_key=submission_key).first()
        if existing:
            if existing.task_id != task.pk:
                raise ValidationError('Submission key belongs to another task')
            return existing, False
        job = GradingJob(task=task, submission_key=submission_key, kind=kind, text=text, reference_text=reference_text)
        if audio is not None:
            if audio.size > settings.AI_MAX_AUDIO_BYTES:
                raise ValidationError('Audio too large')
            job.audio = audio
        job.save()
        return job, True


def expire_jobs(now=None):
    now = now or timezone.now()
    return GradingJob.objects.filter(
        status__in=[GradingJob.Status.QUEUED, GradingJob.Status.PROCESSING],
        submitted_at__lte=now - timedelta(seconds=settings.AI_DEADLINE_SECONDS),
    ).update(status=GradingJob.Status.MANUAL, fallback_reason='ai_deadline_exceeded', finished_at=now)


def process_job(job_id, provider=None):
    now = timezone.now()
    expire_jobs(now)
    claimed = GradingJob.objects.filter(pk=job_id, status=GradingJob.Status.QUEUED).update(
        status=GradingJob.Status.PROCESSING, started_at=now,
    )
    if not claimed:
        return False
    job = GradingJob.objects.get(pk=job_id)
    try:
        remaining = (job.ai_deadline - timezone.now()).total_seconds()
        if remaining <= 0:
            raise TimeoutError()
        result = validate_result((provider or OpenAIGrader()).grade(
            job, timeout=min(settings.AI_REQUEST_TIMEOUT_SECONDS, remaining),
        ), job.kind)
        finished = timezone.now()
        if finished >= job.ai_deadline:
            raise TimeoutError()
        scores = [result[k] for k in ('vocabulary', 'grammar', 'pronunciation') if result[k] is not None]
        GradingJob.objects.filter(pk=job_id, status=GradingJob.Status.PROCESSING).update(
            status=GradingJob.Status.AI_REVIEWED, result=result,
            suggested_score=round(sum(scores) / len(scores), 2), finished_at=finished,
        )
    except Exception as exc:
        reason = 'ai_timeout' if isinstance(exc, TimeoutError) else 'ai_error'
        logger.warning('AI fallback job=%s error_type=%s', job_id, type(exc).__name__)
        GradingJob.objects.filter(pk=job_id, status=GradingJob.Status.PROCESSING).update(
            status=GradingJob.Status.MANUAL, fallback_reason=reason, finished_at=timezone.now(),
        )
    return True

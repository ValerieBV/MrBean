import json
import math
from django.core.exceptions import ValidationError
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from .models import GradingJob
from .permissions import staff_required, tasks_for
from .services import enqueue_submission


def serialize(job):
    return {
        'id': job.pk, 'submission_key': job.submission_key, 'task_id': job.task_id,
        'learner_id': job.task.learner_id, 'title': job.task.title, 'kind': job.kind,
        'status': job.status, 'submitted_at': job.submitted_at.isoformat(),
        'sla_deadline': job.sla_deadline.isoformat(), 'result': job.result,
        'suggested_score': job.suggested_score, 'final_score': job.final_score,
        'teacher_feedback': job.teacher_feedback, 'fallback_reason': job.fallback_reason,
        'text': job.text, 'reference_text': job.reference_text,
        'audio_url': f'/ai/jobs/{job.pk}/audio/' if job.audio else None,
    }


@require_POST
def submit(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'authentication_required'}, status=401)
    try:
        data = json.loads(request.body) if request.content_type == 'application/json' else request.POST
        if not isinstance(data, dict) and request.content_type == 'application/json':
            raise ValueError()
        task = get_object_or_404(tasks_for(request.user), pk=int(data.get('task_id')))
        job, created = enqueue_submission(
            task=task, submission_key=data.get('submission_key'), kind=data.get('kind'),
            text=data.get('text', ''), reference_text=data.get('reference_text', ''),
            audio=request.FILES.get('audio'),
        )
    except (ValueError, TypeError, ValidationError):
        return JsonResponse({'error': 'invalid_submission'}, status=400)
    return JsonResponse(serialize(job), status=201 if created else 200)


@require_GET
def detail(request, job_id):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'authentication_required'}, status=401)
    job = get_object_or_404(GradingJob.objects.select_related('task').filter(task__in=tasks_for(request.user)), pk=job_id)
    return JsonResponse(serialize(job))


@require_GET
def audio(request, job_id):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'authentication_required'}, status=401)
    job = get_object_or_404(GradingJob.objects.filter(task__in=tasks_for(request.user)), pk=job_id)
    if not job.audio:
        return JsonResponse({'error': 'no_audio'}, status=404)
    try:
        response = FileResponse(job.audio.open('rb'))
        response['Cache-Control'] = 'private, no-store'
        return response
    except FileNotFoundError:
        return JsonResponse({'error': 'no_audio'}, status=404)


@require_POST
@staff_required
def review(request, job_id):
    try:
        data = json.loads(request.body)
        score, feedback = data['score'], data['feedback']
        if type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 10:
            raise ValueError()
        if not isinstance(feedback, str) or not feedback.strip() or len(feedback) > 10000:
            raise ValueError()
    except (ValueError, TypeError, KeyError):
        return JsonResponse({'error': 'invalid_review'}, status=400)
    with transaction.atomic():
        job = get_object_or_404(GradingJob.objects.select_for_update().filter(task__in=tasks_for(request.user)), pk=job_id)
        if job.status not in ('manual', 'ai_reviewed'):
            return JsonResponse({'error': 'not_reviewable'}, status=409)
        changed = GradingJob.objects.filter(pk=job.pk, status__in=['manual', 'ai_reviewed']).update(
            status='graded', final_score=score, teacher_feedback=feedback,
            reviewed_by=request.user, finished_at=timezone.now(),
        )
        if not changed:
            return JsonResponse({'error': 'not_reviewable'}, status=409)
        job.refresh_from_db()
    return JsonResponse(serialize(job))

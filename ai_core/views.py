import json
import math
from django.core.exceptions import ValidationError
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST
from .models import GradingJob, VocabularyPage
from .permissions import staff_required, tasks_for, is_manager
from .services import enqueue_submission


def serialize(job):
    return {
        'id': job.pk, 'submission_key': job.submission_key, 'task_id': job.task_id,
        'learner_id': job.task.learner_id, 'learner_name': job.task.learner.get_full_name() or job.task.learner.username,
        'title': job.task.title, 'kind': job.kind, 'status': job.status,
        'status_label': job.get_status_display(), 'submitted_at': job.submitted_at.isoformat(),
        'result': job.result, 'suggested_score': job.suggested_score, 'final_score': job.final_score,
        'teacher_feedback': job.teacher_feedback, 'text': job.text, 'transcript': job.transcript,
        'reference_text': job.reference_text, 'grading_method': job.grading_method,
        'reviewed_at': job.finished_at.isoformat() if job.finished_at else None,
        'detail_url': reverse('submissions:result', args=[job.pk]),
        'audio_url': reverse('ai_core:audio', args=[job.pk]) if job.audio else None,
    }


@require_POST
def submit(request, task_id=None):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'authentication_required'}, status=401)
    if request.user.role != 'student' or request.user.is_superuser:
        return JsonResponse({'error': 'student_submission_required'}, status=403)
    try:
        data = json.loads(request.body) if request.content_type == 'application/json' else request.POST
        if not hasattr(data, 'get'):
            raise ValueError()
        task = get_object_or_404(tasks_for(request.user).filter(assignment__isnull=False,
            assignment__classroom__is_active=True, assignment__classroom__enrollments__student=request.user,
            assignment__classroom__enrollments__status='active', assigned_at__lte=timezone.now()), pk=int(task_id if task_id is not None else data.get('task_id')))
        answers = data.get('answers', {})
        if isinstance(answers, str):
            answers = json.loads(answers)
        job, created = enqueue_submission(task=task, submission_key=data.get('submission_key'),
            text=data.get('text', ''), audio=request.FILES.get('audio'),
            answers=answers, images=request.FILES.getlist('images'), reference_version=data.get('reference_version'))
    except (ValueError, TypeError, ValidationError) as exc:
        return JsonResponse({'error': 'invalid_submission', 'message': '; '.join(exc.messages) if isinstance(exc, ValidationError) else 'Dữ liệu không hợp lệ.'}, status=400)
    return JsonResponse(serialize(job), status=201 if created else 200)


@require_GET
def detail(request, job_id):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'authentication_required'}, status=401)
    job = get_object_or_404(GradingJob.objects.select_related('task__learner').filter(task__in=tasks_for(request.user)), pk=job_id)
    response = JsonResponse(serialize(job))
    response['Cache-Control'] = 'private, no-store'
    return response


@require_GET
def audio(request, job_id):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'authentication_required'}, status=401)
    job = get_object_or_404(GradingJob.objects.filter(task__in=tasks_for(request.user)), pk=job_id)
    if not job.audio:
        return JsonResponse({'error': 'no_audio'}, status=404)
    return private_file(job.audio)


def private_file(field):
    try:
        response = FileResponse(field.open('rb'))
        response['Cache-Control'] = 'private, no-store'
        response['X-Content-Type-Options'] = 'nosniff'
        return response
    except FileNotFoundError:
        return JsonResponse({'error': 'file_missing'}, status=404)


@require_GET
def image(request, page_id):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'authentication_required'}, status=401)
    page = get_object_or_404(VocabularyPage.objects.filter(job__task__in=tasks_for(request.user)), pk=page_id)
    return private_file(page.image)


@require_POST
@staff_required
def review(request, job_id):
    # Managers monitor; admin/superuser and assigned teachers confirm scores.
    if request.user.role == 'manager' and not request.user.is_superuser:
        return JsonResponse({'error': 'grading_for_teacher_or_admin'}, status=403)
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
        job = get_object_or_404(GradingJob.objects.select_for_update().select_related('task__learner').filter(task__in=tasks_for(request.user)), pk=job_id)
        if job.status not in ('manual', 'ai_reviewed'):
            return JsonResponse({'error': 'not_reviewable'}, status=409)
        changed = GradingJob.objects.filter(pk=job.pk, status__in=['manual', 'ai_reviewed']).update(
            status='graded', final_score=score, teacher_feedback=feedback,
            reviewed_by=request.user, finished_at=timezone.now(), grading_method='teacher')
        if not changed:
            return JsonResponse({'error': 'not_reviewable'}, status=409)
        job.refresh_from_db()
        if job.progress_id and not GradingJob.objects.filter(progress_id=job.progress_id,
                submitted_at__gte=job.submitted_at).exclude(pk=job.pk).filter(Q(submitted_at__gt=job.submitted_at) | Q(pk__gt=job.pk)).exists():
            type(job.progress).objects.filter(pk=job.progress_id).update(score=score*10)
        from accounts.notifications import notify
        notify(recipient=job.task.learner, sender=request.user, title='Đã có điểm: '+job.task.title,
            message=feedback, target_url=reverse('submissions:result',args=[job.pk]), event_key=f'result:{job.pk}')
    return JsonResponse(serialize(job))


@require_GET
def reference_video(request, job_id):
    if not request.user.is_authenticated:
        return JsonResponse({'error':'authentication_required'},status=401)
    job=get_object_or_404(GradingJob.objects.filter(task__in=tasks_for(request.user)),pk=job_id)
    return private_path(job.rubric_snapshot.get('video_name',''))


def private_path(name):
    from django.core.files.storage import default_storage
    if not name:
        return JsonResponse({'error':'file_missing'},status=404)
    try:
        response=FileResponse(default_storage.open(name,'rb'))
        response['Cache-Control']='private, no-store'
        response['X-Content-Type-Options']='nosniff'
        return response
    except (FileNotFoundError,ValueError):
        return JsonResponse({'error':'file_missing'},status=404)

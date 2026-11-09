import json
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils import timezone
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST
from .models import GradingJob, VocabularyPage
from .permissions import staff_required, tasks_for, is_manager
from .services import enqueue_submission


def assessment_result(result):
    if not isinstance(result, dict):
        return {}
    allowed = {'needs_manual','feedback','complete','comparison','pronunciation','details','expected_total','matched_total','correct_count','total','missing_count','transcript','transcript_source'}
    clean = {key:value for key,value in result.items() if key in allowed}
    if isinstance(clean.get('comparison'), dict):
        clean['comparison'] = {key:value for key,value in clean['comparison'].items() if key != 'score'}
    return clean


def serialize(job, *, include_ai=True):
    if not include_ai:
        from .reporting import report_job
        return report_job(job)
    return {
        'id': job.pk, 'submission_key': job.submission_key, 'task_id': job.task_id,
        'learner_id': job.task.learner_id, 'learner_name': job.task.learner.get_full_name() or job.task.learner.username,
        'title': job.task.title, 'kind': job.kind, 'status': job.status,
        'status_label': job.public_status_label, 'submitted_at': job.submitted_at.isoformat(),
        'result': assessment_result(job.result),
        'completion_status': job.completion_status,
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
    return JsonResponse(serialize(job, include_ai=False), status=201 if created else 200)


@require_GET
def detail(request, job_id):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'authentication_required'}, status=401)
    job = get_object_or_404(GradingJob.objects.select_related('task__learner').filter(task__in=tasks_for(request.user)), pk=job_id)
    include_ai = request.user.is_superuser or request.user.role in ('admin', 'teacher')
    response = JsonResponse(serialize(job, include_ai=include_ai))
    response['Cache-Control'] = 'private, no-store'
    return response


@require_GET
def audio(request, job_id):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'authentication_required'}, status=401)
    job = get_object_or_404(GradingJob.objects.filter(task__in=tasks_for(request.user)), pk=job_id)
    if not job.audio:
        return JsonResponse({'error': 'no_audio'}, status=404)
    return private_file(job.audio, request)


def private_file(field, request=None):
    try:
        from core.media import private_media_response
        response = private_media_response(field.open('rb'), request)
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
    # Managers monitor; admin/superuser and assigned teachers confirm completion.
    if request.user.role == 'manager' and not request.user.is_superuser:
        return JsonResponse({'error': 'grading_for_teacher_or_admin'}, status=403)
    try:
        data = json.loads(request.body)
        feedback, completion = data['feedback'], data['completion_status']
        if completion not in ('complete', 'incomplete'):
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
            status='graded', final_score=None, teacher_feedback=feedback,
            reviewed_by=request.user, finished_at=timezone.now(), grading_method='teacher',
            completion_status=completion, completion_confirmed_at=timezone.now(), completion_confirmed_by=request.user)
        if not changed:
            return JsonResponse({'error': 'not_reviewable'}, status=409)
        job.refresh_from_db()
        from submissions.progress import sync_progress
        sync_progress(job)
        from accounts.notifications import notify
        notify(recipient=job.task.learner, sender=request.user, title='Đã có kết quả: '+job.task.title,
            message=feedback, target_url=reverse('submissions:result',args=[job.pk]), event_key=f'result:{job.pk}')
    return JsonResponse(serialize(job))


@require_POST
@staff_required
def confirm_completion(request, job_id):
    if request.user.role == 'manager' and not request.user.is_superuser:
        return JsonResponse({'error': 'grading_for_teacher_or_admin'}, status=403)
    try:
        completion = json.loads(request.body)['completion_status']
        if completion not in ('complete', 'incomplete'):
            raise ValueError()
    except (ValueError, TypeError, KeyError):
        return JsonResponse({'error': 'invalid_completion'}, status=400)
    with transaction.atomic():
        job = get_object_or_404(GradingJob.objects.select_for_update().filter(task__in=tasks_for(request.user)), pk=job_id)
        if job.status != 'graded' or job.completion_status != 'pending':
            return JsonResponse({'error': 'completion_already_confirmed'}, status=409)
        job.completion_status = completion
        job.completion_confirmed_at = timezone.now()
        job.completion_confirmed_by = request.user
        job.save(update_fields=['completion_status', 'completion_confirmed_at', 'completion_confirmed_by'])
        from submissions.progress import sync_progress
        sync_progress(job)
        from accounts.notifications import notify
        notify(recipient=job.task.learner, sender=request.user, title='Đã xác nhận mức hoàn thành: '+job.task.title,
            message=job.get_completion_status_display(), target_url=reverse('submissions:result', args=[job.pk]),
            event_key=f'completion:{job.pk}')
    return JsonResponse(serialize(job))


@require_GET
def reference_video(request, job_id):
    if not request.user.is_authenticated:
        return JsonResponse({'error':'authentication_required'},status=401)
    job=get_object_or_404(GradingJob.objects.filter(task__in=tasks_for(request.user)),pk=job_id)
    return private_path(job.rubric_snapshot.get('video_name',''), request)


def private_path(name, request=None):
    from django.core.files.storage import default_storage
    if not name:
        return JsonResponse({'error':'file_missing'},status=404)
    try:
        from core.media import private_media_response
        response=private_media_response(default_storage.open(name,'rb'), request)
        response['Cache-Control']='private, no-store'
        response['X-Content-Type-Options']='nosniff'
        return response
    except (FileNotFoundError,ValueError):
        return JsonResponse({'error':'file_missing'},status=404)


def private_pdf(name, request=None):
    response = private_path(name, request)
    if response.status_code in (200, 206):
        response['Content-Type'] = 'application/pdf'
        response['X-Frame-Options'] = 'SAMEORIGIN'
    return response


@require_GET
def listening_material(request, job_id, exercise_id, kind):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'authentication_required'}, status=401)
    from django.http import Http404
    job = get_object_or_404(GradingJob.objects.filter(task__in=tasks_for(request.user), kind='listening'), pk=job_id)
    exercise = next((x for x in job.rubric_snapshot.get('exercises', []) if x['id'] == exercise_id), None)
    if not exercise or kind not in ('audio', 'document'):
        raise Http404
    return private_pdf(exercise.get('document_name', ''), request) if kind == 'document' else private_path(exercise.get('audio_name', ''), request)

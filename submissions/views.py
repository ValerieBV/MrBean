import json
import uuid
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Prefetch
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST
from ai_core.models import GradingJob
from ai_core.permissions import tasks_for


@login_required
def student_dashboard(request):
    return redirect('dashboard:index')


@login_required
def do_task(request, task_id):
    if request.user.role != 'student':
        raise PermissionDenied
    task = get_object_or_404(tasks_for(request.user).select_related('assignment__lesson', 'assignment__classroom').filter(
        assignment__isnull=False, assignment__classroom__is_active=True,
        assignment__classroom__enrollments__student=request.user, assignment__classroom__enrollments__status='active',
        assigned_at__lte=timezone.now()), pk=task_id)
    # Render only student-visible question fields; never serialize correct answers into HTML.
    rubric = task.assignment.rubric
    from .models import LessonProgress
    progress = LessonProgress.objects.filter(student=request.user, lesson=task.assignment.lesson).first()
    draft = progress.draft if progress and progress.draft_valid else {}
    from assignments.models import ListeningQuestion
    image_ids = set(ListeningQuestion.objects.filter(lesson=task.assignment.lesson).exclude(image='').exclude(image__isnull=True).values_list('pk', flat=True))
    questions = [{**{k: q[k] for k in ('id','question_text','option_a','option_b','option_c','option_d')}, 'has_image': q['id'] in image_ids} for q in rubric.get('questions', [])]
    return render(request, 'submissions/do_task.html', {'task': task, 'rubric': rubric,
        'questions': questions,
        'submission_key': uuid.uuid4().hex, 'draft_text': draft.get('text', '') if isinstance(draft, dict) else ''})


@login_required
def result(request, job_id):
    job = get_object_or_404(GradingJob.objects.select_related('task__learner','task__assignment__classroom').filter(
        task__in=tasks_for(request.user)), pk=job_id)
    can_review = (request.user.is_superuser or request.user.role in ('admin','teacher')) and job.status in ('manual','ai_reviewed')
    return render(request, 'submissions/result.html', {'job': job, 'can_review': can_review})


@login_required
@require_POST
def autosave(request, task_id):
    if request.user.role != 'student':
        raise PermissionDenied
    task = get_object_or_404(tasks_for(request.user).filter(assignment__isnull=False, assigned_at__lte=timezone.now()), pk=task_id)
    try:
        data = json.loads(request.body)
        if not isinstance(data, dict) or not isinstance(data.get('text',''), str) or len(data.get('text',''))>20000:
            raise ValueError()
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'error':'invalid_draft'}, status=400)
    from .models import LessonProgress
    progress, _ = LessonProgress.objects.get_or_create(student=request.user, lesson=task.assignment.lesson)
    progress.draft, progress.draft_saved_at = {'text': data.get('text','')}, timezone.now()
    progress.save(update_fields=['draft','draft_saved_at'])
    return JsonResponse({'ok':True})


@login_required
def lesson_audio(request, task_id):
    task = get_object_or_404(tasks_for(request.user).filter(assignment__isnull=False), pk=task_id)
    from ai_core.views import private_file
    if not task.assignment.lesson.audio_file:
        from django.http import Http404
        raise Http404
    return private_file(task.assignment.lesson.audio_file)


@login_required
def lesson_image(request, task_id, question_id):
    task = get_object_or_404(tasks_for(request.user).filter(assignment__isnull=False), pk=task_id)
    from assignments.models import ListeningQuestion
    from ai_core.views import private_file
    from django.http import Http404
    if question_id not in [q['id'] for q in task.assignment.rubric.get('questions', [])]:
        raise Http404
    question = get_object_or_404(ListeningQuestion, pk=question_id, lesson=task.assignment.lesson)
    if not question.image:
        raise Http404
    return private_file(question.image)

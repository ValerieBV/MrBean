import json
import uuid
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.http import JsonResponse, Http404
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST
from assignments.listening import FIRST_NUMBER
from ai_core.models import GradingJob
from ai_core.permissions import tasks_for
from .access import submission_problem, assert_can_submit, is_unlocked
from .models import LessonProgress


def student_only(user):
    if user.role != 'student' or user.is_superuser: raise PermissionDenied


def own_task(request, task_id):
    student_only(request.user)
    return get_object_or_404(tasks_for(request.user).select_related('learner', 'assignment__lesson',
        'assignment__classroom', 'exemption').filter(assignment__isnull=False), pk=task_id)


@login_required
def student_dashboard(request):
    student_only(request.user)
    from courses.models import Enrollment
    classes=[{'code':e.classroom.class_code,'name':e.classroom.name,'term':e.classroom.course.name,
              'color':'#1f3a93'} for e in Enrollment.objects.filter(student=request.user,status='active').select_related('classroom__course')]
    return render(request,'submissions/student_dashboard.html',{'classes':classes,'current_class':None})


@login_required
def student_home(request, skill=None):
    student_only(request.user)
    from assignments.models import Skill
    from dashboard.services import annotated_tasks
    from .context import current_enrollment
    enrollment=current_enrollment(request)
    rows = annotated_tasks(request.user, {}).filter(assignment__isnull=False)
    rows=rows.filter(assignment__classroom_id=enrollment.classroom_id) if enrollment else rows.none()
    if skill is None:
        cards=[]
        for value,label in Skill.choices:
            items=rows.filter(assignment__lesson__skill=value)
            required=items.filter(exemption__isnull=True)
            total=required.count();done=required.filter(confirmed_completion='complete').count()
            cards.append({'skill':value,'label':label,'total':total,'done':done,
                'exempt':items.filter(exemption__isnull=False).count(),'pct':round(done*100/total) if total else 0})
        return render(request,'submissions/student_home.html',{'cards':cards})
    if skill not in Skill.values:raise Http404
    if skill in Skill.values: rows = rows.filter(assignment__lesson__skill=skill)
    page = Paginator(rows.order_by('assignment__lesson__skill', 'assignment__lesson__order', 'pk'), 20).get_page(request.GET.get('page'))
    for task in page:
        task.blocked_reason = submission_problem(task)
    return render(request, 'submissions/student_skill.html', {'tasks':page,'skill':skill,'skill_label':dict(Skill.choices)[skill],
        'rows':[{'task':task,'lesson':task.assignment.lesson,'completed':task.confirmed_completion=='complete',
                 'incomplete':task.confirmed_completion=='incomplete',
                 'has_submission':bool(task.latest_job_id), 'completion_pending':task.confirmed_completion=='pending',
                 'pending':task.latest_status in ('queued','processing','ai_reviewed','manual'),
                 'unlocked':not task.blocked_reason,'reason':task.blocked_reason,'result_id':task.latest_job_id} for task in page]})


@login_required
def enter_class(request, code):
    student_only(request.user)
    from courses.models import Enrollment
    enrollment = get_object_or_404(Enrollment, student=request.user, status='active', classroom__class_code=code)
    request.session['learning_class_id']=enrollment.classroom_id
    return redirect('submissions:student_home')


@login_required
def do_lesson(request, pk):
    student_only(request.user)
    task = get_object_or_404(tasks_for(request.user).filter(assignment__lesson_id=pk,
        assignment__classroom__enrollments__student=request.user,
        assignment__classroom__enrollments__status='active', assigned_at__lte=timezone.now()).order_by('-assigned_at'))
    return redirect('submissions:do_task', task_id=task.pk)


def listening_question_number(question, exercise_kinds, fallback=1):
    start = FIRST_NUMBER.get(exercise_kinds.get(question.get('exercise_id')), 1)
    return question.get('source_number') or start + question.get('number', fallback) - 1


@login_required
def do_task(request, task_id):
    task = own_task(request, task_id)
    if task.assigned_at > timezone.now():
        return render(request, 'submissions/upcoming_task.html', {'task': task})
    rubric = task.assignment.rubric
    video_embed_url = rubric.get('video_embed_url', '')
    from assignments.video import youtube_embed
    try:
        if rubric.get('youtube_url'): video_embed_url = youtube_embed(rubric['youtube_url'])
    except (ValidationError, ValueError): video_embed_url = ''
    reading_ready = bool(rubric.get('mode') == 'repeat_video' and rubric.get('reference_transcript') and
        (video_embed_url or rubric.get('video_name')))
    draft = task.draft if task.draft_valid and isinstance(task.draft, dict) else {}
    answers = draft.get('answers', {})
    questions = []
    exercise_kinds = {item['id']:item.get('kind') for item in rubric.get('exercises', [])}
    for q in rubric.get('questions', []):
        saved = answers.get(str(q['id']), '')
        selected = saved.get('chosen', '') if isinstance(saved, dict) else saved
        row = {**{k: q.get(k, '') for k in ('id','question_text','option_a','option_b','option_c','option_d','exercise_id')},
            'has_image':bool(q.get('image_name')), 'selected':selected,
            'short_answer':saved.get('short_answer', '') if isinstance(saved, dict) else '',
            'requires_short_answer':q.get('requires_short_answer', False), 'number':listening_question_number(q, exercise_kinds, len(questions)+1)}
        exercise_kind = exercise_kinds.get(q.get('exercise_id'))
        row['options'] = [{'letter':c, 'text':q.get('option_'+c.lower(), '')} for c in q.get('choice_letters','ABCD')
            if q.get('option_'+c.lower())]
        if exercise_kind == 'part2':
            row.update(question_text='', has_image=False, options=[{'letter':c,'text':c} for c in 'ABC'])
        row['has_printed_options'] = any(option['text'] != option['letter'] for option in row['options'])
        questions.append(row)
    listening_exercises = [{**{k:e.get(k) for k in ('id','order','kind','label','title','question_count')},
        'has_audio':bool(e.get('audio_name')), 'has_document':bool(e.get('document_name')) and e.get('kind') != 'part2',
        'questions':[q for q in questions if q['exercise_id']==e['id']]} for e in rubric.get('exercises',[])]
    if not listening_exercises and questions:
        listening_exercises = [{'id':None, 'order':1, 'title':'Bài nghe', 'label':'Nội dung đã giao',
            'has_audio':bool(rubric.get('audio_name')), 'has_document':False, 'questions':questions}]
    from ai_core.reporting import report_job
    jobs=list(task.jobs.order_by('-submitted_at','-pk')[:10])
    for job in jobs:job.public_status=report_job(job)['status_label']
    return render(request, 'submissions/do_'+{'listening':'listening','speaking':'speaking','vocabulary':'vocab'}[rubric['skill']]+'.html', {'task': task, 'lesson':task.assignment.lesson, 'rubric': rubric, 'questions': questions,
        'video_embed_url': video_embed_url, 'reading_ready': reading_ready, 'listening_exercises':listening_exercises,
        'blocked_reason': submission_problem(task), 'is_late': task.due_at < timezone.now(),
        'pending_exemption': task.assignment.exemption_requests.filter(enrollment__student=request.user, status='pending').first(),
        'jobs':jobs,'word_details':rubric.get('word_details') or [{'word':word} for word in rubric.get('words',[])],
        'submission_key': uuid.uuid4().hex, 'draft_text': draft.get('text', ''),
        'draft_saved_at': task.draft_saved_at if draft else None})


@login_required
def result(request, job_id):
    from ai_core.reporting import report_job
    from ai_core.diagnostics import staff_grading_state
    job = get_object_or_404(GradingJob.objects.select_related('task__learner','task__assignment__classroom').filter(
        task__in=tasks_for(request.user)), pk=job_id)
    can_review = (request.user.is_superuser or request.user.role in ('admin','teacher')) and job.status in ('manual','ai_reviewed')
    ai_trial = None
    if (request.user.is_superuser or request.user.role in ('admin','teacher')) and job.kind in ('speaking','vocabulary'):
        available = isinstance(job.result, dict) and (job.status == 'ai_reviewed' or job.status == 'graded' and type(job.result.get('complete')) is bool) and isinstance(job.result.get('feedback'), str) and bool(job.result.get('feedback'))
        complete = job.result.get('complete') if available and type(job.result.get('complete')) is bool else None
        ai_trial = {'available': available, 'complete':complete, 'label':{True:'Hoàn thành',False:'Chưa hoàn thành',None:'Cần giáo viên kiểm tra'}[complete],
                    'feedback': job.result.get('feedback','') if available else '',
                    'pending': job.status in ('queued','processing'), 'status': job.status}
    from assignments.video import youtube_embed
    try: video_url = youtube_embed(job.rubric_snapshot.get('youtube_url',''))
    except (ValidationError, ValueError): video_url = ''
    questions = {q['id']:q for q in job.rubric_snapshot.get('questions',[])}
    exercise_kinds = {item['id']:item.get('kind') for item in job.rubric_snapshot.get('exercises', [])}
    listening_details = [{**row,'question_text':questions.get(row.get('question_id'),{}).get('question_text',''),
        'number':listening_question_number(questions.get(row.get('question_id'),{}), exercise_kinds),
        'exercise_order':questions.get(row.get('question_id'),{}).get('exercise_order')}
        for row in job.result.get('details',[]) if isinstance(row,dict)] if job.kind=='listening' else []
    return render(request, 'submissions/result.html', {'job': job, 'can_review': can_review, 'published':report_job(job),
        'ai_trial':ai_trial, 'can_confirm_completion':(request.user.is_superuser or request.user.role in ('admin','teacher')) and job.status=='graded' and job.completion_status=='pending',
        'staff_grading_state':staff_grading_state(job) if request.user.is_superuser or request.user.role in ('admin','manager','teacher') else None,
        'can_ask_tutor':request.user.role=='student' and not request.user.is_superuser and job.status=='graded',
        'reference_video_url':video_url, 'listening_details':listening_details})


@login_required
@require_POST
def autosave(request, task_id=None, pk=None):
    if pk is not None:
        task = get_object_or_404(tasks_for(request.user).filter(assignment__lesson_id=pk,
            assignment__classroom__enrollments__student=request.user, assignment__classroom__enrollments__status='active'))
        task_id = task.pk
    task = own_task(request, task_id)
    if task.assignment.rubric.get('skill') == 'speaking':
        return JsonResponse({'error':'recording_only', 'message':'Bài đọc theo video chỉ nhận ghi âm.'}, status=400)
    try:
        with transaction.atomic():
            task = type(task).objects.select_for_update().select_related('learner','assignment__lesson','assignment__classroom').get(pk=task.pk)
            assert_can_submit(task)
            data = json.loads(request.body)
            if not isinstance(data, dict) or not isinstance(data.get('text',''), str) or len(data.get('text','')) > 20000:
                raise ValueError()
            if data.get('reference_version') != task.assignment.reference_version:
                raise ValidationError('Đề đã được cập nhật. Hãy tải lại trang trước khi tiếp tục.')
            answers = data.get('answers', {})
            if not isinstance(answers, dict): raise ValueError()
            if task.assignment.rubric.get('skill') == 'listening':
                from .grading import grade_listening
                result = grade_listening(task.assignment.rubric.get('questions', []), answers)
                answers = {str(row['question_id']): {'chosen':row['chosen'], 'short_answer':row['short_answer']} for row in result['details']}
            elif answers:
                raise ValueError()
            draft = {'text': data.get('text','') if task.assignment.rubric.get('skill')=='vocabulary' else '', 'answers': answers}
            LessonProgress.objects.get_or_create(student=request.user, lesson=task.assignment.lesson)
            task.draft, task.draft_saved_at = draft, timezone.now()
            task.save(update_fields=['draft', 'draft_saved_at'])
    except (ValueError, UnicodeDecodeError, ValidationError) as exc:
        return JsonResponse({'error':'invalid_draft', 'message': '; '.join(exc.messages) if isinstance(exc, ValidationError) else 'Bản nháp không hợp lệ.'}, status=400)
    return JsonResponse({'ok':True, 'saved_at':task.draft_saved_at.isoformat()})


@login_required
@require_POST
def submit_lesson(request, pk):
    student_only(request.user)
    task = get_object_or_404(tasks_for(request.user).filter(assignment__lesson_id=pk,
        assignment__classroom__enrollments__student=request.user, assignment__classroom__enrollments__status='active'))
    from ai_core.views import submit
    return submit(request, task_id=task.pk)


def media_task(request, task_id):
    task = get_object_or_404(tasks_for(request.user).select_related('learner', 'assignment__lesson', 'assignment__classroom'),
        pk=task_id, assignment__isnull=False, assigned_at__lte=timezone.now())
    if request.user.role == 'student':
        if not is_unlocked(task) or not task.assignment.classroom.enrollments.filter(student=request.user, status='active').exists():
            raise Http404
    return task


@login_required
def lesson_audio(request, task_id):
    task = media_task(request, task_id)
    from ai_core.views import private_path
    # Fallback reads historical rubrics created before media snapshots were introduced.
    return private_path(task.assignment.rubric.get('audio_name', task.assignment.lesson.audio_file.name or ''), request)


@login_required
def lesson_video(request, task_id):
    task = media_task(request, task_id)
    from ai_core.views import private_path
    return private_path(task.assignment.rubric.get('video_name', ''), request)


@login_required
def lesson_image(request, task_id, question_id):
    task = media_task(request, task_id)
    from ai_core.views import private_path
    question = next((q for q in task.assignment.rubric.get('questions', []) if q['id']==question_id), None)
    if not question: raise Http404
    return private_path(question.get('image_name', ''))


@login_required
def listening_material(request, task_id, exercise_id, kind):
    task = media_task(request, task_id)
    from ai_core.views import private_path, private_pdf
    exercise = next((x for x in task.assignment.rubric.get('exercises', []) if x['id']==exercise_id), None)
    if not exercise or kind not in ('audio','document'):
        raise Http404
    return private_pdf(exercise.get('document_name', ''), request) if kind=='document' else private_path(exercise.get('audio_name', ''), request)

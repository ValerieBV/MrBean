from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Max, Count
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from ai_core.permissions import is_manager, classes_for
from .models import Lesson, ClassAssignment, VocabWord, ListeningQuestion, SpeakingTask, Skill
from .forms import (LessonForm, VocabWordForm, ListeningQuestionForm, SpeakingTaskForm,
                    AssignmentForm, AssignmentUpdateForm, ReadingReferenceForm)
from .services import assign_to_class

ITEMS = {'vocabulary': (VocabWordForm, VocabWord, 'words'),
         'listening': (ListeningQuestionForm, ListeningQuestion, 'questions'),
         'speaking': (SpeakingTaskForm, SpeakingTask, 'speaking_tasks')}


def staff(user):
    if not (is_manager(user) or user.role == 'teacher'):
        raise PermissionDenied


def editable_lessons(user):
    return Lesson.objects.all() if is_manager(user) else Lesson.objects.filter(created_by=user)


def assert_editable(request, lesson):
    if not (is_manager(request.user) or lesson.created_by_id == request.user.pk):
        raise PermissionDenied
    if lesson.class_assignments.exists() or lesson.progress.exists():
        raise ValidationError('Bài đã giao được giữ nguyên. Dùng chức năng sao chép để tạo phiên bản mới.')


@login_required
def assignment_list(request, skill=None):
    staff(request.user)
    lessons = Lesson.objects.all().select_related('created_by').order_by('skill', 'program', 'order')
    skill = skill or request.GET.get('skill', '')
    if not skill and not request.GET.get('q'):
        return render(request,'assignments/assignment_list.html',{'cards':[
            {'skill':value,'label':label,'count':lessons.filter(skill=value).count()} for value,label in Skill.choices]})
    if skill in Skill.values: lessons = lessons.filter(skill=skill)
    query = request.GET.get('q', '').strip()[:100]
    if query: lessons = lessons.filter(Q(title__icontains=query) | Q(description__icontains=query))
    page=Paginator(lessons,20).get_page(request.GET.get('page'))
    for lesson in page:
        lesson.can_edit_contents=(is_manager(request.user) or lesson.created_by_id==request.user.pk) and not (lesson.class_assignments.exists() or lesson.progress.exists())
    return render(request, 'assignments/skill_lessons.html' if skill in Skill.values else 'assignments/list.html', {
        'lessons':page,'skill':skill,'skill_label':dict(Skill.choices).get(skill,''),
        'skill_filter': skill, 'query': query, 'skill_choices': Skill.choices})


@login_required
def lesson_create(request, skill=None):
    staff(request.user)
    form = LessonForm(request.POST or None, request.FILES or None, initial={'skill': skill or 'vocabulary'})
    if request.method == 'POST' and form.is_valid():
        lesson = form.save(commit=False); lesson.created_by = request.user; lesson.save()
        messages.success(request, 'Đã tạo buổi học. Thêm nội dung trước khi giao cho lớp.')
        return redirect('assignments:lesson_detail', pk=lesson.pk)
    return render(request, 'assignments/lesson_form.html', {'form': form, 'title': 'Tạo buổi học',
        'skill':skill or form['skill'].value(),'skill_label':dict(Skill.choices).get(skill or form['skill'].value(),''),
        'back_url': reverse('assignments:assignment_list')})


@login_required
def lesson_update(request, pk):
    staff(request.user)
    lesson = get_object_or_404(editable_lessons(request.user), pk=pk)
    try: assert_editable(request, lesson)
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages)); return redirect('assignments:lesson_detail', pk=pk)
    form = LessonForm(request.POST or None, request.FILES or None, instance=lesson)
    if request.method == 'POST' and form.is_valid():
        form.save(); messages.success(request, 'Đã cập nhật buổi học.')
        return redirect('assignments:lesson_detail', pk=pk)
    return render(request, 'assignments/lesson_form.html', {'form': form, 'title': 'Chỉnh sửa buổi học',
        'skill':lesson.skill,'skill_label':lesson.get_skill_display(),
        'back_url': reverse('assignments:lesson_detail', args=[pk])})


@login_required
def lesson_detail(request, pk):
    staff(request.user)
    lesson = get_object_or_404(Lesson, pk=pk)
    can_edit = (is_manager(request.user) or lesson.created_by_id == request.user.pk) and not (lesson.class_assignments.exists() or lesson.progress.exists())
    form_cls, _, relation = ITEMS[lesson.skill]
    form = form_cls(request.POST or None, request.FILES or None)
    if request.method == 'POST':
        if not can_edit: raise PermissionDenied
        if form.is_valid():
            item = form.save(commit=False); item.lesson = lesson; item.save()
            messages.success(request, 'Đã thêm nội dung.')
            return redirect('assignments:lesson_detail', pk=pk)
    return render(request, 'assignments/lesson_detail.html', {'lesson': lesson, 'items': getattr(lesson, relation).all(),
        'form': form, 'can_edit': can_edit,
        'reading_assignments': lesson.class_assignments.filter(classroom__in=classes_for(request.user)).select_related('classroom')})


@login_required
def lesson_delete(request, pk):
    staff(request.user)
    lesson = get_object_or_404(editable_lessons(request.user), pk=pk)
    try: assert_editable(request, lesson)
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages)); return redirect('assignments:lesson_detail', pk=pk)
    if request.method == 'POST':
        lesson.delete(); messages.success(request, 'Đã xóa buổi chưa giao.')
        return redirect('assignments:assignment_list')
    return render(request, 'assignments/confirm_delete.html', {'title': 'Xóa buổi học chưa giao', 'description': str(lesson),
        'back_url': reverse('assignments:lesson_detail', args=[pk])})


@login_required
def lesson_clone(request, pk):
    staff(request.user)
    source = get_object_or_404(Lesson, pk=pk)
    if request.method == 'POST':
        with transaction.atomic():
            maximum = Lesson.objects.filter(skill=source.skill, program=source.program).aggregate(value=Max('order'))['value'] or 0
            data = {f.name: getattr(source, f.name) for f in Lesson._meta.fields
                    if f.name not in ('id', 'created_at', 'updated_at', 'created_by', 'order', 'title')}
            lesson = Lesson.objects.create(**data, order=maximum+1, title=(source.title+' (bản sao)')[:200], created_by=request.user)
            _, _, relation = ITEMS[source.skill]
            for item in getattr(source, relation).all():
                item.pk = None; item.lesson = lesson; item.save()
        messages.success(request, 'Đã sao chép thành buổi mới. Bản gốc và các lượt giao cũ được giữ nguyên.')
        return redirect('assignments:lesson_detail', pk=lesson.pk)
    return render(request, 'core/confirm.html', {'title': 'Sao chép buổi học', 'description': str(source),
        'button_label': 'Tạo bản sao', 'back_url': reverse('assignments:lesson_detail', args=[pk])})


@login_required
def item_edit(request, skill, pk, delete=False):
    staff(request.user)
    if skill not in ITEMS: raise PermissionDenied
    form_cls, model, _ = ITEMS[skill]
    item = get_object_or_404(model.objects.select_related('lesson'), pk=pk)
    try: assert_editable(request, item.lesson)
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages)); return redirect('assignments:lesson_detail', pk=item.lesson_id)
    back = reverse('assignments:lesson_detail', args=[item.lesson_id])
    if delete:
        if request.method == 'POST':
            item.delete(); messages.success(request, 'Đã xóa nội dung.'); return redirect(back)
        return render(request, 'core/confirm.html', {'title': 'Xóa nội dung', 'description': str(item), 'back_url': back})
    form = form_cls(request.POST or None, request.FILES or None, instance=item)
    if request.method == 'POST' and form.is_valid():
        form.save(); messages.success(request, 'Đã cập nhật nội dung.'); return redirect(back)
    return render(request, 'assignments/form.html', {'form': form, 'title': 'Chỉnh sửa nội dung', 'back_url': back})


@login_required
def assign(request):
    staff(request.user)
    form = AssignmentForm(request.POST or None, user=request.user, initial={'lesson': request.GET.get('lesson'),
        'classroom': request.GET.get('classroom')})
    if request.method == 'POST' and form.is_valid():
        try:
            saved = assign_to_class(actor=request.user, **form.cleaned_data)
            messages.success(request, 'Đã giao bài và tạo danh sách bài cần nộp cho học viên đang học trong lớp.')
            return redirect('assignments:assigned_detail', pk=saved.pk)
        except ValidationError as exc: form.add_error(None, exc)
    return render(request, 'assignments/form.html', {'form': form, 'title': 'Giao bài cho lớp',
        'back_url': reverse('assignments:assigned_list')})


@login_required
def assigned_list(request):
    staff(request.user)
    rows = ClassAssignment.objects.filter(classroom__in=classes_for(request.user)).select_related('lesson', 'classroom', 'classroom__teacher').annotate(
        task_count=Count('tasks', distinct=True)).order_by('-assigned_at','-pk')
    if request.GET.get('classroom'): rows = rows.filter(classroom_id=request.GET['classroom']) if request.GET['classroom'].isdigit() else rows.none()
    if request.GET.get('skill') in Skill.values: rows = rows.filter(lesson__skill=request.GET['skill'])
    return render(request, 'assignments/assigned_list.html', {'assignments': Paginator(rows, 20).get_page(request.GET.get('page')),
        'classes': classes_for(request.user), 'skill_choices': Skill.choices})


@login_required
def assigned_detail(request, pk):
    staff(request.user)
    assignment = get_object_or_404(ClassAssignment.objects.select_related('lesson', 'classroom', 'classroom__teacher').filter(
        classroom__in=classes_for(request.user)), pk=pk)
    from django.db.models import Prefetch
    from ai_core.models import GradingJob
    tasks = assignment.tasks.select_related('learner', 'exemption').prefetch_related(Prefetch('jobs', queryset=GradingJob.objects.order_by('-submitted_at', '-pk')))
    return render(request, 'assignments/assigned_detail.html', {'assignment': assignment, 'tasks': tasks})


@login_required
def assigned_update(request, pk):
    staff(request.user)
    assignment = get_object_or_404(ClassAssignment.objects.select_related('classroom').filter(classroom__in=classes_for(request.user)), pk=pk)
    form = AssignmentUpdateForm(request.POST or None, instance=assignment)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            saved = form.save()
            saved.tasks.update(due_at=saved.due_at)
        messages.success(request, 'Đã cập nhật hạn nộp và quy định nhận bài.')
        return redirect('assignments:assigned_detail', pk=pk)
    return render(request, 'assignments/form.html', {'form': form, 'title': 'Cập nhật lượt giao · '+assignment.classroom.class_code,
        'back_url': reverse('assignments:assigned_detail', args=[pk])})


@login_required
def reading_reference(request, pk):
    staff(request.user)
    assignment = get_object_or_404(ClassAssignment.objects.select_related('lesson', 'classroom').filter(
        classroom__in=classes_for(request.user), lesson__skill='speaking'), pk=pk)
    initial = {'youtube_url': assignment.rubric.get('youtube_url', ''),
        'reference_transcript': assignment.rubric.get('reference_transcript', '')}
    form = ReadingReferenceForm(request.POST or None, request.FILES or None, initial=initial, assignment=assignment)
    if request.method == 'POST' and form.is_valid():
        data = form.cleaned_data.copy(); video = data.pop('video_file', None)
        with transaction.atomic():
            locked = ClassAssignment.objects.select_for_update().get(pk=assignment.pk)
            if video: locked.reference_video = video
            if data.get('youtube_url') and not video:
                locked.reference_video = ''
            data['video_name'] = locked.reference_video.name if locked.reference_video else ''
            if data['video_name']:
                data['video_embed_url'] = ''; data['youtube_url'] = ''
            locked.rubric = {**locked.rubric, **data, 'skill': 'speaking', 'mode': 'repeat_video'}
            # Save uploaded file before freezing its final storage name in the rubric.
            locked.save()
            if locked.reference_video:
                locked.rubric['video_name'] = locked.reference_video.name
                locked.save(update_fields=['rubric'])
        messages.success(request, 'Đã cập nhật mẫu cho các lần nộp mới. Đề và kết quả của bài đã nộp được giữ nguyên.')
        return redirect('assignments:assigned_detail', pk=pk)
    return render(request, 'assignments/form.html', {'form': form, 'title': 'Mẫu đọc theo video · '+assignment.classroom.class_code,
        'back_url': reverse('assignments:assigned_detail', args=[pk])})


@login_required
def lesson_media(request, pk, kind):
    staff(request.user)
    lesson = get_object_or_404(Lesson, pk=pk)
    from ai_core.views import private_file
    from django.http import Http404
    field = lesson.audio_file if kind == 'audio' else lesson.video_file
    if not field: raise Http404
    return private_file(field)


@login_required
def question_image(request, pk):
    staff(request.user)
    question = get_object_or_404(ListeningQuestion, pk=pk)
    from ai_core.views import private_file
    from django.http import Http404
    if not question.image: raise Http404
    return private_file(question.image)

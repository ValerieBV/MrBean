from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST
from ai_core.permissions import is_manager, classes_for
from .models import Lesson, ClassAssignment, VocabWord, ListeningQuestion, SpeakingTask
from .forms import LessonForm, VocabWordForm, ListeningQuestionForm, SpeakingTaskForm, AssignmentForm
from .services import assign_to_class


def staff(user):
    if not (is_manager(user) or user.role == 'teacher'):
        raise PermissionDenied


def editable_lessons(user):
    rows = Lesson.objects.all()
    return rows if is_manager(user) else rows.filter(created_by=user)


@login_required
def assignment_list(request):
    staff(request.user)
    lessons = Lesson.objects.all().order_by('skill', 'program', 'order')
    skill = request.GET.get('skill')
    if skill in ('listening', 'speaking', 'vocabulary'):
        lessons = lessons.filter(skill=skill)
    return render(request, 'assignments/list.html', {'lessons': lessons, 'can_edit_all': is_manager(request.user)})


@login_required
def lesson_create(request, skill=None):
    staff(request.user)
    form = LessonForm(request.POST or None, request.FILES or None, initial={'skill': skill or 'vocabulary'})
    if request.method == 'POST' and form.is_valid():
        lesson = form.save(commit=False)
        lesson.created_by = request.user
        lesson.save()
        return redirect('assignments:lesson_detail', pk=lesson.pk)
    return render(request, 'assignments/form.html', {'form': form, 'title': 'Tạo buổi học'})


@login_required
def lesson_update(request, pk):
    staff(request.user)
    lesson = get_object_or_404(editable_lessons(request.user), pk=pk)
    if lesson.class_assignments.exists():
        messages.error(request, 'Bài đã được giao. Tạo buổi mới để thay đổi nội dung; yêu cầu và đáp án đã giao được giữ nguyên.')
        return redirect('assignments:lesson_detail', pk=pk)
    form = LessonForm(request.POST or None, request.FILES or None, instance=lesson)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('assignments:lesson_detail', pk=pk)
    return render(request, 'assignments/form.html', {'form': form, 'title': 'Chỉnh sửa buổi học'})


@login_required
def lesson_detail(request, pk):
    staff(request.user)
    lesson = get_object_or_404(Lesson, pk=pk)
    can_edit = (is_manager(request.user) or lesson.created_by_id == request.user.pk) and not lesson.class_assignments.exists()
    form_cls, relation = {'vocabulary': (VocabWordForm, 'words'), 'listening': (ListeningQuestionForm, 'questions'), 'speaking': (SpeakingTaskForm, 'speaking_tasks')}[lesson.skill]
    form = form_cls(request.POST or None, request.FILES or None)
    if request.method == 'POST':
        if not can_edit:
            raise PermissionDenied
        if form.is_valid():
            item = form.save(commit=False)
            item.lesson = lesson
            item.save()
            return redirect('assignments:lesson_detail', pk=pk)
    return render(request, 'assignments/detail.html', {'lesson': lesson, 'items': getattr(lesson, relation).all(),
        'form': form, 'can_edit': can_edit})


@login_required
def assign(request):
    staff(request.user)
    form = AssignmentForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        try:
            assign_to_class(actor=request.user, **form.cleaned_data)
            messages.success(request, 'Đã giao bài và tạo roster cho toàn bộ học viên đang học trong lớp.')
            return redirect('dashboard:index')
        except ValidationError as exc:
            form.add_error(None, exc)
    return render(request, 'assignments/form.html', {'form': form, 'title': 'Giao bài cho lớp'})

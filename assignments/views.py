from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect

from .models import Lesson, VocabWord, ListeningQuestion, SpeakingTask, Skill
from .forms import LessonForm, VocabWordForm, ListeningQuestionForm, SpeakingTaskForm


def staff_required(view):
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        role = getattr(request.user, "role", None)
        if role == "student" and not request.user.is_staff:
            messages.error(request, "Bạn không có quyền truy cập khu quản trị.")
            return redirect("submissions:student_home")
        return view(request, *args, **kwargs)
    return wrapper


SKILL_LABELS = dict(Skill.choices)


@staff_required
def assignment_list(request):
    cards = []
    for value, label in Skill.choices:
        cards.append({
            "skill": value,
            "label": label,
            "count": Lesson.objects.filter(skill=value).count(),
        })
    return render(request, "assignments/assignment_list.html", {"cards": cards})


@staff_required
def skill_lessons(request, skill):
    lessons = Lesson.objects.filter(skill=skill)
    return render(request, "assignments/skill_lessons.html", {
        "skill": skill, "skill_label": SKILL_LABELS.get(skill, skill), "lessons": lessons,
    })


@staff_required
def lesson_create(request, skill):
    initial = {"skill": skill, "order": Lesson.objects.filter(skill=skill).count() + 1}
    form = LessonForm(request.POST or None, request.FILES or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        lesson = form.save(commit=False)
        lesson.created_by = request.user
        lesson.save()
        messages.success(request, "Đã tạo buổi học. Giờ thêm nội dung cho buổi.")
        return redirect("lesson_detail", pk=lesson.pk)
    return render(request, "assignments/lesson_form.html", {
        "form": form, "skill": skill, "skill_label": SKILL_LABELS.get(skill, skill),
        "title": "Tạo buổi mới",
    })


@staff_required
def lesson_update(request, pk):
    lesson = get_object_or_404(Lesson, pk=pk)
    form = LessonForm(request.POST or None, request.FILES or None, instance=lesson)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Đã cập nhật buổi học.")
        return redirect("lesson_detail", pk=lesson.pk)
    return render(request, "assignments/lesson_form.html", {
        "form": form, "skill": lesson.skill, "skill_label": lesson.get_skill_display(),
        "title": "Sửa buổi học", "lesson": lesson,
    })


@staff_required
def lesson_delete(request, pk):
    lesson = get_object_or_404(Lesson, pk=pk)
    skill = lesson.skill
    if request.method == "POST":
        lesson.delete()
        messages.success(request, "Đã xóa buổi học.")
        return redirect("skill_lessons", skill=skill)
    return render(request, "assignments/confirm_delete.html", {
        "object_name": str(lesson), "back_url": "skill_lessons", "back_arg": skill,
    })


@staff_required
def lesson_detail(request, pk):
    lesson = get_object_or_404(Lesson, pk=pk)

    if lesson.skill == Skill.VOCABULARY:
        form_cls, rel = VocabWordForm, "words"
    elif lesson.skill == Skill.LISTENING:
        form_cls, rel = ListeningQuestionForm, "questions"
    else:
        form_cls, rel = SpeakingTaskForm, "speaking_tasks"

    items = getattr(lesson, rel).all()
    initial = {"order": items.count() + 1}
    form = form_cls(request.POST or None, request.FILES or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        item = form.save(commit=False)
        item.lesson = lesson
        item.save()
        messages.success(request, "Đã thêm nội dung.")
        return redirect("lesson_detail", pk=lesson.pk)

    return render(request, "assignments/lesson_detail.html", {
        "lesson": lesson, "items": items, "form": form,
    })


@staff_required
def item_delete(request, skill, pk):
    model_map = {"vocabulary": VocabWord, "listening": ListeningQuestion, "speaking": SpeakingTask}
    model = model_map.get(skill)
    item = get_object_or_404(model, pk=pk)
    lesson_pk = item.lesson.pk
    item.delete()
    messages.success(request, "Đã xóa nội dung.")
    return redirect("lesson_detail", pk=lesson_pk)

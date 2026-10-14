import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from assignments.models import Lesson, Skill
from .models import LessonProgress, QuestionResponse, SpeakingRecording

SKILL_LABELS = dict(Skill.choices)

MOCK_CLASSES = [
    {"code": "ELC3001_49K22.1", "name": "Luyện thi TOEIC 500+", "cert": "TOEIC", "term": "Kỳ 1 năm học 2025-2026", "color": "#2980b9"},
    {"code": "ELC3002_49K22.2", "name": "Tiếng Anh B1 cấp tốc", "cert": "B1", "term": "Kỳ 1 năm học 2025-2026", "color": "#16a085"},
    {"code": "ELC3003_49K22.3", "name": "Ôn thi VSTEP B2", "cert": "VSTEP", "term": "Kỳ hè năm học 2025-2026", "color": "#8e44ad"},
]


def _get_progress(student, lesson):
    return LessonProgress.objects.filter(student=student, lesson=lesson).first()


def _find_class(code):
    return next((c for c in MOCK_CLASSES if c["code"] == code), None)


def is_unlocked(student, lesson):
    prev = (
        Lesson.objects.filter(
            skill=lesson.skill, program=lesson.program, order__lt=lesson.order, is_active=True
        )
        .order_by("-order")
        .first()
    )
    if prev is None:
        return True
    p = _get_progress(student, prev)
    return bool(p and p.is_completed)


@login_required
def student_dashboard(request):
    request.session.pop("current_class", None)
    return render(request, "submissions/student_dashboard.html", {"classes": MOCK_CLASSES})


@login_required
def enter_class(request, code):
    cls = _find_class(code)
    if cls:
        request.session["current_class"] = cls
    return redirect("submissions:student_home")


@login_required
def student_home(request):
    cards = []
    for value, label in Skill.choices:
        total = Lesson.objects.filter(skill=value, is_active=True).count()
        done = LessonProgress.objects.filter(
            student=request.user, lesson__skill=value, status="completed"
        ).count()
        pct = round(done / total * 100) if total else 0
        cards.append({"skill": value, "label": label, "total": total, "done": done, "pct": pct})
    return render(request, "submissions/student_home.html", {"cards": cards})


@login_required
def student_skill(request, skill):
    lessons = Lesson.objects.filter(skill=skill, is_active=True)
    rows = []
    for lesson in lessons:
        progress = _get_progress(request.user, lesson)
        rows.append({
            "lesson": lesson,
            "unlocked": is_unlocked(request.user, lesson),
            "completed": bool(progress and progress.is_completed),
        })
    return render(request, "submissions/student_skill.html", {
        "skill": skill, "skill_label": SKILL_LABELS.get(skill, skill), "rows": rows,
    })


@login_required
def do_lesson(request, pk):
    lesson = get_object_or_404(Lesson, pk=pk, is_active=True)
    if not is_unlocked(request.user, lesson):
        messages.error(request, "Bạn cần hoàn thành buổi trước để mở buổi này.")
        return redirect("submissions:student_skill", skill=lesson.skill)

    progress, _ = LessonProgress.objects.get_or_create(student=request.user, lesson=lesson)
    draft = progress.draft if progress.draft_valid else {}

    tpl = {
        Skill.VOCABULARY: "submissions/do_vocab.html",
        Skill.LISTENING: "submissions/do_listening.html",
        Skill.SPEAKING: "submissions/do_speaking.html",
    }[lesson.skill]
    return render(request, tpl, {"lesson": lesson, "progress": progress, "draft": draft})


@login_required
@require_POST
def autosave(request, pk):
    progress = get_object_or_404(LessonProgress, lesson_id=pk, student=request.user)
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"ok": False}, status=400)
    progress.draft = data
    progress.draft_saved_at = timezone.now()
    progress.save(update_fields=["draft", "draft_saved_at"])
    return JsonResponse({"ok": True, "saved_at": timezone.localtime().strftime("%H:%M:%S")})


@login_required
@require_POST
def submit_lesson(request, pk):
    lesson = get_object_or_404(Lesson, pk=pk, is_active=True)
    progress, _ = LessonProgress.objects.get_or_create(student=request.user, lesson=lesson)

    if lesson.skill == Skill.LISTENING:
        _submit_listening(request, lesson, progress)
    elif lesson.skill == Skill.SPEAKING:
        _submit_speaking(request, lesson, progress)

    progress.status = LessonProgress.Status.COMPLETED
    progress.completed_at = timezone.now()
    progress.draft = {}
    progress.save()
    messages.success(request, "Đã hoàn thành buổi học! Buổi tiếp theo đã được mở.")
    return redirect("submissions:student_skill", skill=lesson.skill)


def _submit_listening(request, lesson, progress):
    correct = 0
    total = 0
    for q in lesson.questions.all():
        total += 1
        chosen = request.POST.get(f"q_{q.id}_opt", "").strip().upper()
        filled = request.POST.get(f"q_{q.id}_fill", "").strip()
        is_correct = None
        if lesson.listening_type == "part12" and q.correct_option:
            is_correct = (chosen == q.correct_option)
            if is_correct:
                correct += 1
        QuestionResponse.objects.update_or_create(
            progress=progress, question=q,
            defaults={"chosen_option": chosen, "filled_text": filled, "is_correct": is_correct},
        )
    if lesson.listening_type == "part12" and total:
        progress.score = round(correct / total * 100, 1)


def _submit_speaking(request, lesson, progress):
    for task in lesson.speaking_tasks.all():
        f = request.FILES.get(f"task_{task.id}_audio")
        if f:
            SpeakingRecording.objects.update_or_create(
                progress=progress, task=task, defaults={"audio": f}
            )

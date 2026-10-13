# Create your views here.

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Q

from .models import assignment


# Danh sách ngân hàng bài tập
@staff_member_required
def assignment_list(request):
    keyword = request.GET.get("q", "").strip()

    assignments = assignment.objects.all()

    if keyword:
        assignments = assignments.filter(
            Q(code__icontains=keyword)
            | Q(title__icontains=keyword)
        )

    category = request.GET.get("category", "")
    if category:
        assignments = assignments.filter(category=category)

    program = request.GET.get("program", "")
    if program:
        assignments = assignments.filter(program=program)

    context = {
        "assignments": assignments,
        "keyword": keyword,
        "category_choices": assignment.CATEGORY_CHOICES,
        "program_choices": assignment.PROGRAM_CHOICES,
        "selected_category": category,
        "selected_program": program,
    }

    return render(
        request,
        "assignments/assignment_list.html",
        context,
    )


# Thêm bài tập
@staff_member_required
def assignment_create(request):
    if request.method == "POST":
        code = request.POST.get("code", "").strip()
        title = request.POST.get("title", "").strip()
        category = request.POST.get("category", "")
        program = request.POST.get("program", "")
        description = request.POST.get("description", "")
        content = request.POST.get("content", "")
        answer_key = request.POST.get("answer_key", "")
        audio_file = request.FILES.get("audio_file")
        attachment = request.FILES.get("attachment")

        if not code or not title or not category:
            messages.error(
                request,
                "Vui lòng nhập mã, tên và danh mục bài tập.",
            )
        elif assignment.objects.filter(code=code).exists():
            messages.error(request, "Mã bài tập đã tồn tại.")
        elif category == "practice_test" and not program:
            messages.error(
                request,
                "Vui lòng chọn chương trình cho kho luyện đề.",
            )
        else:
            assignment.objects.create(
                code=code,
                title=title,
                category=category,
                program=program if category == "practice_test" else "",
                description=description,
                content=content,
                answer_key=answer_key,
                audio_file=audio_file,
                attachment=attachment,
                created_by=request.user,
            )

            messages.success(request, "Thêm bài tập thành công.")
            return redirect("assignment_list")

    context = {
        "category_choices": assignment.CATEGORY_CHOICES,
        "program_choices": assignment.PROGRAM_CHOICES,
    }

    return render(
        request,
        "assignments/assignment_form.html",
        context,
    )


# Sửa bài tập
@staff_member_required
def assignment_update(request, pk):
    assignment = get_object_or_404(assignment, pk=pk)

    if request.method == "POST":
        code = request.POST.get("code", "").strip()
        title = request.POST.get("title", "").strip()
        category = request.POST.get("category", "")
        program = request.POST.get("program", "")

        if not code or not title or not category:
            messages.error(
                request,
                "Vui lòng nhập mã, tên và danh mục bài tập.",
            )
        elif assignment.objects.filter(code=code).exclude(pk=pk).exists():
            messages.error(request, "Mã bài tập đã tồn tại.")
        elif category == "practice_test" and not program:
            messages.error(
                request,
                "Vui lòng chọn chương trình cho kho luyện đề.",
            )
        else:
            assignment.code = code
            assignment.title = title
            assignment.category = category
            assignment.program = (
                program if category == "practice_test" else ""
            )
            assignment.description = request.POST.get("description", "")
            assignment.content = request.POST.get("content", "")
            assignment.answer_key = request.POST.get("answer_key", "")

            if request.FILES.get("audio_file"):
                assignment.audio_file = request.FILES["audio_file"]

            if request.FILES.get("attachment"):
                assignment.attachment = request.FILES["attachment"]

            assignment.save()

            messages.success(request, "Cập nhật bài tập thành công.")
            return redirect("assignment_list")

    context = {
        "assignment": assignment,
        "category_choices": assignment.CATEGORY_CHOICES,
        "program_choices": assignment.PROGRAM_CHOICES,
    }

    return render(
        request,
        "assignments/assignment_form.html",
        context,
    )


# Xóa bài tập
@staff_member_required
def assignment_delete(request, pk):
    assignment = get_object_or_404(assignment, pk=pk)

    if request.method == "POST":
        assignment.delete()
        messages.success(request, "Xóa bài tập thành công.")
        return redirect("assignment_list")

    return render(
        request,
        "assignments/assignment_confirm_delete.html",
        {"assignment": assignment},
    )

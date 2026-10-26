from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Count, ProtectedError
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_POST
from accounts.models import CustomUser
from accounts.permissions import role_required
from ai_core.permissions import classes_for, is_manager
from .models import Course, ClassRoom, Enrollment, ExemptionRequest
from .forms import (CourseForm, ClassRoomForm, AssignTeacherForm, EnrollStudentForm, EnrollmentStatusForm,
                    ExemptionRequestForm, ExemptionReviewForm)
from .services import ClassManagementService, ExemptionControlService


@role_required('admin', 'manager')
def course_list(request):
    rows = Course.objects.annotate(class_count=Count('classes')).order_by('code')
    return render(request, 'courses/course_list.html', {'courses': rows})


@role_required('admin', 'manager')
def course_form(request, pk=None):
    course = get_object_or_404(Course, pk=pk) if pk else None
    form = CourseForm(request.POST or None, instance=course)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Đã lưu khóa học.')
        return redirect('courses:course_list')
    return render(request, 'core/form.html', {'form': form,
        'title': 'Cập nhật khóa học' if pk else 'Tạo khóa học', 'back_url': reverse('courses:course_list')})


@role_required('admin', 'manager')
def course_delete(request, pk):
    course = get_object_or_404(Course, pk=pk)
    if request.method == 'POST':
        try:
            course.delete()
            messages.success(request, 'Đã xóa khóa học chưa có lớp.')
        except ProtectedError:
            messages.error(request, 'Khóa học đã có lớp. Cần giữ khóa học để bảo toàn lịch sử.')
        return redirect('courses:course_list')
    return render(request, 'core/confirm.html', {'title': 'Xóa khóa học chưa sử dụng',
        'description': str(course), 'back_url': reverse('courses:course_list')})


@login_required
def class_list_view(request):
    rows = classes_for(request.user).select_related('course', 'teacher').annotate(
        active_students=Count('enrollments', filter=Q(enrollments__status='active'))).order_by('-created_at','pk')
    query = request.GET.get('q', '').strip()[:100]
    if query:
        rows = rows.filter(Q(class_code__icontains=query) | Q(name__icontains=query) | Q(course__name__icontains=query))
    if request.GET.get('status') == 'active': rows = rows.filter(is_active=True)
    if request.GET.get('status') == 'closed': rows = rows.filter(is_active=False)
    student_enrollments = Enrollment.objects.filter(student=request.user, status='active').select_related(
        'classroom__course', 'classroom__teacher', 'exemption_quota') if request.user.role == 'student' else None
    student_exemptions = ExemptionRequest.objects.filter(enrollment__student=request.user).select_related(
        'enrollment__classroom__course', 'reviewed_by', 'assignment__lesson') if student_enrollments is not None else None
    return render(request, 'courses/class_list.html', {'classes': Paginator(rows, 20).get_page(request.GET.get('page')),
        'query': query, 'student_enrollments': student_enrollments,
        'student_exemptions': Paginator(student_exemptions,20).get_page(request.GET.get('history_page'))
            if student_exemptions is not None else None})


@login_required
def class_detail_view(request, class_id):
    classroom = get_object_or_404(classes_for(request.user).select_related('course', 'teacher'), pk=class_id)
    enrollments = classroom.enrollments.select_related('student', 'exemption_quota')
    pending = ExemptionRequest.objects.filter(enrollment__classroom=classroom, status='pending').select_related(
        'enrollment__student', 'enrollment__exemption_quota')
    if request.user.role == 'student' and not request.user.is_superuser:
        enrollments = enrollments.filter(student=request.user)
    own_enrollment = enrollments.filter(student=request.user).first() if request.user.role == 'student' else None
    return render(request, 'courses/class_detail.html', {'classroom': classroom, 'enrollments': enrollments,
        'can_manage': is_manager(request.user), 'pending_exemptions':pending,
        'is_teacher_of_class':request.user.is_superuser or request.user.role == 'admin' or classroom.teacher_id == request.user.pk,
        'student_quota':getattr(own_enrollment,'exemption_quota',None),
        'assignments': classroom.assignments.select_related('lesson').order_by('-assigned_at')[:20]})


@role_required('admin', 'manager')
def class_create_view(request):
    return _class_form(request)


@role_required('admin', 'manager')
def class_update_view(request, class_id):
    return _class_form(request, get_object_or_404(ClassRoom, pk=class_id))


def _class_form(request, classroom=None):
    was_active = classroom.is_active if classroom else False
    form = ClassRoomForm(request.POST or None, instance=classroom, initial={'course':request.GET.get('course')} if not classroom else None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            saved = form.save(commit=False)
            if not saved.pk: saved.created_by = request.user
            saved.save()
            if saved.teacher:
                ClassManagementService.assign_teacher_to_class(saved, saved.teacher)
            if was_active and not saved.is_active:
                saved.enrollments.filter(status='active').update(status='completed')
        messages.success(request, 'Đã lưu thông tin lớp. Lớp ngừng hoạt động vẫn giữ đầy đủ điểm và lịch sử.')
        return redirect('courses:class_detail', class_id=saved.pk)
    return render(request, 'courses/class_form.html', {'form': form, 'classroom':classroom,
        'title': 'Cập nhật lớp học' if classroom else 'Tạo lớp học',
        'back_url': reverse('courses:class_list')})


@role_required('admin', 'manager')
def enrollment_update(request, pk):
    enrollment = get_object_or_404(Enrollment.objects.select_related('student','classroom'), pk=pk)
    form = EnrollmentStatusForm(request.POST or None, initial={'status':enrollment.status})
    if request.method == 'POST' and form.is_valid():
        try:
            status = form.cleaned_data['status']
            if status == 'active' and enrollment.status != 'active':
                ClassManagementService.enroll_student_to_class(enrollment.classroom,enrollment.student)
            elif status != enrollment.status:
                enrollment.status = status
                enrollment.save(update_fields=['status'])
            messages.success(request,'Đã cập nhật ghi danh; lịch sử bài làm được giữ nguyên.')
            return redirect('courses:class_detail',class_id=enrollment.classroom_id)
        except ValidationError as exc: form.add_error(None,exc)
    return render(request,'core/form.html',{'form':form,'title':'Ghi danh · '+enrollment.student.username,
        'back_url':reverse('courses:class_detail',args=[enrollment.classroom_id])})


@role_required('admin', 'manager')
def assign_teacher_view(request, class_id):
    classroom = get_object_or_404(ClassRoom, pk=class_id)
    form = AssignTeacherForm(request.POST or None, initial={'teacher': classroom.teacher})
    if request.method == 'POST' and form.is_valid():
        try:
            ClassManagementService.assign_teacher_to_class(classroom, form.cleaned_data['teacher'])
            messages.success(request, 'Đã phân công giáo viên và cập nhật quyền chấm bài của lớp.')
            return redirect('courses:class_detail', class_id=class_id)
        except ValidationError as exc: form.add_error(None, exc)
    return render(request, 'courses/assign_teacher.html', {'form': form, 'classroom':classroom,
        'title': 'Phân công giáo viên · '+classroom.class_code,
        'back_url': reverse('courses:class_detail', args=[class_id])})


@role_required('admin', 'manager')
def enroll_student_view(request, class_id):
    classroom = get_object_or_404(ClassRoom, pk=class_id)
    form = EnrollStudentForm(request.POST or None, classroom=classroom)
    if request.method == 'POST' and form.is_valid():
        try:
            ClassManagementService.enroll_student_to_class(classroom, form.cleaned_data['student'])
            messages.success(request, 'Đã ghi danh và đồng bộ các bài tập đang mở cho học viên.')
            return redirect('courses:class_detail', class_id=class_id)
        except ValidationError as exc: form.add_error(None, exc)
    return render(request, 'courses/enroll_student.html', {'form': form, 'classroom':classroom,
        'title': 'Thêm học viên · '+classroom.class_code,
        'back_url': reverse('courses:class_detail', args=[class_id])})


@role_required('admin', 'manager')
def remove_student_view(request, class_id, student_id):
    enrollment = get_object_or_404(Enrollment.objects.select_related('student', 'classroom'),
        classroom_id=class_id, student_id=student_id)
    if request.method == 'POST':
        try:
            ClassManagementService.remove_student_from_class(enrollment.classroom, enrollment.student)
            messages.success(request, 'Đã chuyển học viên sang trạng thái nghỉ học. Lịch sử được giữ nguyên.')
        except ValidationError as exc: messages.error(request, '; '.join(exc.messages))
        return redirect('courses:class_detail', class_id=class_id)
    return render(request, 'courses/student_confirm_remove.html', {'title': 'Ngừng ghi danh',
        'student':enrollment.student, 'classroom':enrollment.classroom,
        'description': enrollment.student.username+' · '+enrollment.classroom.class_code,
        'back_url': reverse('courses:class_detail', args=[class_id])})


@role_required('student')
def request_exemption_view(request, class_id):
    enrollment = get_object_or_404(Enrollment.objects.select_related('classroom', 'exemption_quota'),
        classroom_id=class_id, classroom__is_active=True, student=request.user, status='active')
    form = ExemptionRequestForm(request.POST or None, student=request.user, classroom=enrollment.classroom,
        initial={'assignment': request.GET.get('assignment')})
    form.instance.enrollment = enrollment
    if request.method == 'POST' and form.is_valid():
        try:
            ExemptionControlService.submit_exemption(student=request.user, classroom=enrollment.classroom,
                assignment=form.cleaned_data['assignment'], reason=form.cleaned_data['reason'])
            messages.success(request, 'Đã gửi đơn xin miễn. Bài này tạm dừng nhận bài trong khi chờ duyệt.')
            return redirect('courses:exemption_list')
        except ValidationError as exc: form.add_error(None, exc)
    return render(request, 'courses/request_exemption.html', {'form': form, 'classroom': enrollment.classroom,
        'quota': enrollment.exemption_quota})


@login_required
def exemption_list_view(request):
    rows = ExemptionRequest.objects.select_related('enrollment__student', 'enrollment__classroom', 'reviewed_by', 'assignment__lesson')
    if request.user.role == 'student' and not request.user.is_superuser:
        rows = rows.filter(enrollment__student=request.user)
    elif not is_manager(request.user):
        rows = rows.filter(enrollment__classroom__in=classes_for(request.user))
    status = request.GET.get('status', '')
    if status: rows = rows.filter(status=status)
    return render(request, 'courses/exemption_list.html', {'exemptions': Paginator(rows, 20).get_page(request.GET.get('page')),
        'status_filter': status, 'status_choices': ExemptionRequest.STATUS_CHOICES})


@role_required('admin', 'teacher')
def exemption_review_view(request, exemption_id):
    exemption = get_object_or_404(ExemptionRequest.objects.select_related('enrollment__classroom',
        'enrollment__student', 'enrollment__exemption_quota').filter(enrollment__classroom__in=classes_for(request.user)), pk=exemption_id)
    if exemption.status != 'pending':
        messages.info(request, 'Đơn đã được xử lý: '+exemption.get_status_display())
        return redirect('courses:exemption_list')
    form = ExemptionReviewForm(request.POST or None, exemption=exemption)
    if request.method == 'POST' and form.is_valid():
        try:
            ExemptionControlService.review(exemption.pk, request.user,
                approve=form.cleaned_data['action']=='approve', note=form.cleaned_data['note'],
                assignment=form.cleaned_data.get('assignment'))
            messages.success(request, 'Đã xử lý đơn và thông báo kết quả cho học viên.')
            return redirect('courses:exemption_list')
        except ValidationError as exc: form.add_error(None, exc)
    return render(request, 'courses/exemption_review.html', {'form': form, 'exemption': exemption,
        'classroom':exemption.enrollment.classroom,
        'quota': exemption.enrollment.exemption_quota})


@role_required('student')
@require_POST
def exemption_cancel(request, exemption_id):
    exemption = get_object_or_404(ExemptionRequest, pk=exemption_id, enrollment__student=request.user)
    try:
        ExemptionControlService.cancel(exemption.pk, request.user)
        messages.success(request, 'Đã hủy đơn. Bạn có thể nộp bài theo quy định của lớp.')
    except ValidationError as exc: messages.error(request, '; '.join(exc.messages))
    return redirect('courses:exemption_list')

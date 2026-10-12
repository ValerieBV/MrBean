from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from courses.models import Course, ClassRoom, Enrollment, StudentExemptionQuota, ExemptionRequest
from courses.forms import ClassRoomForm, AssignTeacherForm, EnrollStudentForm, ExemptionRequestForm, ExemptionReviewForm
from courses.services import ClassManagementService, ExemptionControlService
from accounts.models import CustomUser
from accounts.permissions import role_required, admin_required, manager_required


@login_required
def class_list_view(request):
    """
    Danh sách lớp học phân quyền:
    - Admin, Quản lý: Xem tất cả các lớp học.
    - Giáo viên: Chỉ xem các lớp mình ĐƯỢC PHÂN CÔNG GIẢNG DẠY (để chấm bài, duyệt miễn).
    - Học viên: Chỉ xem các lớp mình ĐANG THEO HỌC.
    """
    user = request.user

    if user.is_superuser or user.role in [CustomUser.ROLE_ADMIN, CustomUser.ROLE_MANAGER]:
        classes = ClassRoom.objects.all().select_related('course', 'teacher')
    elif user.role == CustomUser.ROLE_TEACHER:
        classes = ClassRoom.objects.filter(teacher=user).select_related('course', 'teacher')
    else:  # Student
        classes = ClassRoom.objects.filter(
            enrollments__student=user,
            enrollments__status=Enrollment.STATUS_ACTIVE
        ).select_related('course', 'teacher')

    return render(request, 'courses/class_list.html', {
        'classes': classes,
        'user_role': user.role
    })


@login_required
def class_detail_view(request, class_id):
    """
    Chi tiết lớp học:
    - Hiển thị thông tin lớp, giáo viên phụ trách chấm bài.
    - Danh sách học viên và hạn mức số buổi miễn nghe (Quota).
    """
    classroom = get_object_or_404(
        ClassRoom.objects.select_related('course', 'teacher'),
        id=class_id
    )
    user = request.user

    # Kiểm tra quyền xem chi tiết lớp: Admin, Manager, Giáo viên của lớp, hoặc Học viên trong lớp
    if not (user.is_superuser or user.role in [CustomUser.ROLE_ADMIN, CustomUser.ROLE_MANAGER]):
        if user.role == CustomUser.ROLE_TEACHER and classroom.teacher != user:
            messages.error(request, "Bạn không phụ trách lớp học này.")
            return redirect('courses:class_list')
        if user.role == CustomUser.ROLE_STUDENT and not classroom.enrollments.filter(student=user, status=Enrollment.STATUS_ACTIVE).exists():
            messages.error(request, "Bạn không tham gia lớp học này.")
            return redirect('courses:class_list')

    enrollments = classroom.enrollments.select_related('student', 'exemption_quota').all()
    can_manage = user.is_superuser or user.role in [CustomUser.ROLE_ADMIN, CustomUser.ROLE_MANAGER]
    is_teacher_of_class = (user == classroom.teacher) or user.is_superuser or user.role == CustomUser.ROLE_ADMIN

    # Đơn xin miễn đang chờ duyệt của lớp này
    pending_exemptions = ExemptionRequest.objects.filter(
        enrollment__classroom=classroom,
        status=ExemptionRequest.STATUS_PENDING
    ).select_related('enrollment__student')

    # Nếu là học viên, lấy thông tin quota của chính mình
    student_quota = None
    if user.role == CustomUser.ROLE_STUDENT:
        my_enrollment = enrollments.filter(student=user).first()
        if my_enrollment:
            student_quota = getattr(my_enrollment, 'exemption_quota', None)

    return render(request, 'courses/class_detail.html', {
        'classroom': classroom,
        'enrollments': enrollments,
        'can_manage': can_manage,
        'is_teacher_of_class': is_teacher_of_class,
        'pending_exemptions': pending_exemptions,
        'student_quota': student_quota,
    })


@role_required(CustomUser.ROLE_ADMIN, CustomUser.ROLE_MANAGER)
def class_create_view(request):
    """Admin hoặc Quản lý tạo lớp học mới"""
    if request.method == 'POST':
        form = ClassRoomForm(request.POST)
        if form.is_valid():
            classroom = form.save(commit=False)
            classroom.created_by = request.user
            classroom.save()
            messages.success(request, f"Đã tạo lớp học '{classroom.name}' ({classroom.class_code}) thành công.")
            return redirect('courses:class_detail', class_id=classroom.id)
    else:
        form = ClassRoomForm()

    return render(request, 'courses/class_form.html', {'form': form, 'title': 'Tạo lớp học mới'})


@role_required(CustomUser.ROLE_ADMIN, CustomUser.ROLE_MANAGER)
def class_update_view(request, class_id):
    """Chỉnh sửa thông tin lớp học"""
    classroom = get_object_or_404(ClassRoom, id=class_id)
    if request.method == 'POST':
        form = ClassRoomForm(request.POST, instance=classroom)
        if form.is_valid():
            form.save()
            messages.success(request, f"Đã cập nhật lớp học '{classroom.name}'.")
            return redirect('courses:class_detail', class_id=classroom.id)
    else:
        form = ClassRoomForm(instance=classroom)

    return render(request, 'courses/class_form.html', {'form': form, 'title': f'Chỉnh sửa lớp: {classroom.class_code}', 'classroom': classroom})


@role_required(CustomUser.ROLE_ADMIN, CustomUser.ROLE_MANAGER)
def assign_teacher_view(request, class_id):
    """
    Phân công giáo viên vào đúng lớp dạy để chấm bài.
    Chỉ cho phép chọn user có role='teacher'.
    """
    classroom = get_object_or_404(ClassRoom, id=class_id)
    if request.method == 'POST':
        form = AssignTeacherForm(request.POST)
        if form.is_valid():
            teacher = form.cleaned_data['teacher']
            try:
                ClassManagementService.assign_teacher_to_class(classroom, teacher)
                messages.success(request, f"Đã phân công giáo viên {teacher.get_full_name() or teacher.username} phụ trách lớp {classroom.class_code}.")
            except ValidationError as e:
                messages.error(request, str(e))
            return redirect('courses:class_detail', class_id=classroom.id)
    else:
        initial = {'teacher': classroom.teacher} if classroom.teacher else {}
        form = AssignTeacherForm(initial=initial)

    return render(request, 'courses/assign_teacher.html', {'form': form, 'classroom': classroom})


@role_required(CustomUser.ROLE_ADMIN, CustomUser.ROLE_MANAGER)
def enroll_student_view(request, class_id):
    """
    Thêm học viên vào lớp học.
    Tự động cấp định mức 08 buổi (TOEIC/VSTEP) hoặc 05 buổi (B1).
    """
    classroom = get_object_or_404(ClassRoom, id=class_id)
    if request.method == 'POST':
        form = EnrollStudentForm(request.POST, classroom=classroom)
        if form.is_valid():
            student = form.cleaned_data['student']
            try:
                ClassManagementService.enroll_student_to_class(classroom, student)
                messages.success(request, f"Đã thêm học viên {student.get_full_name() or student.username} vào lớp {classroom.class_code}.")
            except ValidationError as e:
                messages.error(request, str(e))
            return redirect('courses:class_detail', class_id=classroom.id)
    else:
        form = EnrollStudentForm(classroom=classroom)

    return render(request, 'courses/enroll_student.html', {'form': form, 'classroom': classroom})


@role_required(CustomUser.ROLE_ADMIN, CustomUser.ROLE_MANAGER)
def remove_student_view(request, class_id, student_id):
    """Xóa học viên khỏi lớp học"""
    classroom = get_object_or_404(ClassRoom, id=class_id)
    student = get_object_or_404(CustomUser, id=student_id)
    if request.method == 'POST':
        try:
            ClassManagementService.remove_student_from_class(classroom, student)
            messages.success(request, f"Đã xóa học viên {student.username} khỏi lớp {classroom.class_code}.")
        except ValidationError as e:
            messages.error(request, str(e))
        return redirect('courses:class_detail', class_id=classroom.id)

    return render(request, 'courses/student_confirm_remove.html', {'classroom': classroom, 'student': student})


# ==========================================================
# CƠ CHẾ KIỂM SOÁT MIỄN BTVN NGHE (LISTENING ONLY)
# ==========================================================

@login_required
def request_exemption_view(request, class_id):
    """
    Học viên nộp đơn xin miễn BTVN:
    - Bắt buộc kiểm tra: CHỈ ÁP DỤNG CHO BÀI TẬP NGHE (LISTENING).
    - Kiểm tra số buổi miễn còn lại (> 0).
    """
    classroom = get_object_or_404(ClassRoom, id=class_id)
    user = request.user

    enrollment = Enrollment.objects.filter(
        classroom=classroom,
        student=user,
        status=Enrollment.STATUS_ACTIVE
    ).first()

    if not enrollment:
        messages.error(request, "Bạn không phải học viên đang hoạt động trong lớp này.")
        return redirect('courses:class_detail', class_id=classroom.id)

    quota = getattr(enrollment, 'exemption_quota', None)
    if not quota or quota.remaining_quota <= 0:
        messages.error(request, f"Bạn đã sử dụng hết số buổi miễn BTVN nghe của khóa này ({quota.used_quota if quota else 0}/{quota.max_quota if quota else 0}).")
        return redirect('courses:class_detail', class_id=classroom.id)

    if request.method == 'POST':
        form = ExemptionRequestForm(request.POST)
        if form.is_valid():
            try:
                exemption = ExemptionControlService.submit_listening_exemption(
                    student=user,
                    classroom=classroom,
                    session_title=form.cleaned_data['session_title'],
                    reason=form.cleaned_data['reason']
                )
                messages.success(
                    request,
                    f"Đã gửi đơn xin miễn bài tập nghe '{exemption.session_title}' thành công! "
                    f"Giáo viên phụ trách sẽ xem xét và phê duyệt."
                )
                return redirect('courses:class_detail', class_id=classroom.id)
            except ValidationError as e:
                messages.error(request, str(e))
    else:
        form = ExemptionRequestForm(initial={'homework_type': ExemptionRequest.HOMEWORK_TYPE_LISTENING})

    return render(request, 'courses/request_exemption.html', {
        'form': form,
        'classroom': classroom,
        'quota': quota
    })


@login_required
def exemption_list_view(request):
    """
    Danh sách đơn xin miễn BTVN:
    - Giáo viên: Xem các đơn thuộc các lớp mình đang giảng dạy để duyệt.
    - Quản lý / Admin: Xem toàn bộ các đơn xin miễn để theo dõi, quản trị vận hành.
    - Học viên: Xem các đơn của chính mình.
    """
    user = request.user
    if user.is_superuser or user.role in [CustomUser.ROLE_ADMIN, CustomUser.ROLE_MANAGER]:
        exemptions = ExemptionRequest.objects.all().select_related(
            'enrollment__classroom', 'enrollment__student', 'reviewed_by'
        )
    elif user.role == CustomUser.ROLE_TEACHER:
        # Giáo viên chỉ xem lớp mình phụ trách
        exemptions = ExemptionRequest.objects.filter(
            enrollment__classroom__teacher=user
        ).select_related('enrollment__classroom', 'enrollment__student', 'reviewed_by')
    else:  # Student
        exemptions = ExemptionRequest.objects.filter(
            enrollment__student=user
        ).select_related('enrollment__classroom', 'enrollment__student', 'reviewed_by')

    status_filter = request.GET.get('status', '')
    if status_filter:
        exemptions = exemptions.filter(status=status_filter)

    return render(request, 'courses/exemption_list.html', {
        'exemptions': exemptions,
        'status_filter': status_filter
    })


@role_required(CustomUser.ROLE_ADMIN, CustomUser.ROLE_TEACHER)
def exemption_review_view(request, exemption_id):
    """
    Giáo viên hoặc Admin duyệt / từ chối đơn xin miễn BTVN:
    - Nếu Chấp thuận: Trừ quota, gửi thông báo cho Quản lý và Học viên.
    - Nếu Từ chối: Gửi thông báo kèm lý do cho Học viên.
    """
    exemption = get_object_or_404(
        ExemptionRequest.objects.select_related('enrollment__classroom', 'enrollment__student', 'enrollment__exemption_quota'),
        id=exemption_id
    )
    classroom = exemption.enrollment.classroom

    # Kiểm tra đúng giáo viên lớp hoặc admin
    if not (request.user.is_superuser or request.user.role == CustomUser.ROLE_ADMIN or classroom.teacher == request.user):
        messages.error(request, "Chỉ giáo viên phụ trách lớp này mới có quyền duyệt đơn.")
        return redirect('courses:exemption_list')

    if exemption.status != ExemptionRequest.STATUS_PENDING:
        messages.warning(request, f"Đơn này đã được xử lý ({exemption.get_status_display()}).")
        return redirect('courses:exemption_list')

    if request.method == 'POST':
        form = ExemptionReviewForm(request.POST)
        if form.is_valid():
            action = form.cleaned_data['action']
            note = form.cleaned_data['note']
            try:
                if action == 'approve':
                    ExemptionControlService.approve_exemption(exemption.id, teacher=request.user, note=note)
                    messages.success(request, f"Đã duyệt đơn miễn BTVN Nghe cho học viên {exemption.enrollment.student.username}. Quản lý đã được thông báo.")
                else:
                    ExemptionControlService.reject_exemption(exemption.id, teacher=request.user, reason=note)
                    messages.info(request, f"Đã từ chối đơn miễn BTVN của học viên {exemption.enrollment.student.username}.")
                return redirect('courses:exemption_list')
            except ValidationError as e:
                messages.error(request, str(e))
    else:
        form = ExemptionReviewForm()

    return render(request, 'courses/exemption_review.html', {
        'exemption': exemption,
        'form': form,
        'classroom': classroom,
        'quota': getattr(exemption.enrollment, 'exemption_quota', None)
    })

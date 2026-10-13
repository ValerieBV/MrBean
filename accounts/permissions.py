from functools import wraps
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import redirect
from django.contrib import messages
from accounts.models import CustomUser


def role_required(*allowed_roles):
    """
    Decorator kiểm tra vai trò người dùng (RBAC).
    Chỉ cho phép các user có vai trò trong `allowed_roles` hoặc superuser truy cập.
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped_view(request, *args, **kwargs):
            if request.user.is_superuser or request.user.role in allowed_roles:
                return view_func(request, *args, **kwargs)
            
            # Nếu không đủ quyền, thông báo lỗi và chặn truy cập
            messages.error(request, "Bạn không có quyền thực hiện chức năng này.")
            raise PermissionDenied("Truy cập bị từ chối do không đủ thẩm quyền.")
        return _wrapped_view
    return decorator


def admin_required(view_func):
    """Dành riêng cho Admin toàn quyền"""
    return role_required(CustomUser.ROLE_ADMIN)(view_func)


def manager_required(view_func):
    """Dành cho Quản lý hoặc Admin"""
    return role_required(CustomUser.ROLE_ADMIN, CustomUser.ROLE_MANAGER)(view_func)


def teacher_required(view_func):
    """Dành cho Giáo viên hoặc Admin"""
    return role_required(CustomUser.ROLE_ADMIN, CustomUser.ROLE_TEACHER)(view_func)


def student_required(view_func):
    """Dành cho Học viên"""
    return role_required(CustomUser.ROLE_STUDENT)(view_func)


class RoleRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Mixin bảo vệ Class-Based Views dựa trên vai trò.
    Sử dụng:
    class MyView(RoleRequiredMixin, ListView):
        allowed_roles = [CustomUser.ROLE_ADMIN, CustomUser.ROLE_MANAGER]
    """
    allowed_roles = []

    def test_func(self):
        user = self.request.user
        if not user.is_authenticated:
            return False
        if user.is_superuser or user.role == CustomUser.ROLE_ADMIN:
            return True
        return user.role in self.allowed_roles

    def handle_no_permission(self):
        messages.error(self.request, "Bạn không có quyền thực hiện hành động này.")
        raise PermissionDenied("Bạn không có quyền truy cập trang này.")


# ==========================================================
# CÁC HÀM XÁC THỰC NGHIỆP VỤ TRÁNH GIAO NHẦM BÀI, NHẦM LỚP
# ==========================================================

def can_assign_homework_to_class(user, classroom):
    """
    Kiểm tra người dùng có quyền giao bài tập cho lớp:
    - Admin: Có quyền toàn cục.
    - Quản lý (Manager): Có quyền giao bài tập cho các lớp học.
    - Giáo viên: Chỉ có quyền nếu đúng là giáo viên đang phụ trách lớp đó.
    """
    if not user.is_authenticated:
        return False
    if user.is_superuser or user.role == CustomUser.ROLE_ADMIN:
        return True
    if user.role == CustomUser.ROLE_MANAGER:
        return True
    if user.role == CustomUser.ROLE_TEACHER and classroom.teacher_id == user.id:
        return True
    return False


def can_grade_class_submission(user, classroom):
    """
    Kiểm tra người dùng có quyền chấm điểm cho học viên lớp này không:
    - Admin: Có quyền.
    - Giáo viên: BẮT BUỘC phải là giáo viên phụ trách đúng lớp đó. Tránh chấm nhầm lớp người khác.
    """
    if not user.is_authenticated:
        return False
    if user.is_superuser or user.role == CustomUser.ROLE_ADMIN:
        return True
    if user.role == CustomUser.ROLE_TEACHER and classroom.teacher_id == user.id:
        return True
    return False


def can_approve_exemption_for_class(user, classroom):
    """
    Kiểm tra người dùng có quyền duyệt miễn BTVN cho lớp này không:
    - Admin: Có quyền.
    - Giáo viên: Chỉ giáo viên được phân công dạy lớp đó mới được quyền duyệt miễn.
    """
    return can_grade_class_submission(user, classroom)


def is_student_enrolled_in_class(user, classroom):
    """
    Kiểm tra xem học viên có thực sự thuộc lớp học này không.
    Tránh trường hợp học viên nộp bài hoặc xin miễn bài của lớp khác.
    """
    if not user.is_authenticated or user.role != CustomUser.ROLE_STUDENT:
        return False
    return classroom.enrollments.filter(student=user, status='active').exists()

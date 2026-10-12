from django.contrib.auth.models import AbstractUser
from django.db import models


class CustomUser(AbstractUser):
    # Định nghĩa 4 vai trò theo yêu cầu BRD
    ROLE_ADMIN = 'admin'
    ROLE_MANAGER = 'manager'
    ROLE_TEACHER = 'teacher'
    ROLE_STUDENT = 'student'

    ROLE_CHOICES = (
        (ROLE_ADMIN, 'Admin (Quản trị viên)'),
        (ROLE_MANAGER, 'Quản lý'),
        (ROLE_TEACHER, 'Giáo viên/CTV'),
        (ROLE_STUDENT, 'Học viên'),
    )

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default=ROLE_STUDENT,
        verbose_name="Vai trò"
    )
    phone_number = models.CharField(
        max_length=15,
        blank=True,
        null=True,
        verbose_name="Số điện thoại"
    )

    # Thêm related_name để tránh xung đột với auth.User mặc định của Django
    groups = models.ManyToManyField(
        'auth.Group',
        verbose_name='groups',
        blank=True,
        help_text='The groups this user belongs to. A user will get all permissions granted to each of their groups.',
        related_name="customuser_set",
        related_query_name="user",
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        verbose_name='user permissions',
        blank=True,
        help_text='Specific permissions for this user.',
        related_name="customuser_set",
        related_query_name="user",
    )

    class Meta:
        verbose_name = "Người dùng"
        verbose_name_plural = "Người dùng"

    def __str__(self):
        full_name = self.get_full_name()
        display_name = f"{full_name} ({self.username})" if full_name else self.username
        return f"{display_name} - [{self.get_role_display()}]"

    @property
    def is_admin_user(self):
        return self.role == self.ROLE_ADMIN or self.is_superuser

    @property
    def is_manager_user(self):
        return self.role == self.ROLE_MANAGER

    @property
    def is_teacher_user(self):
        return self.role == self.ROLE_TEACHER

    @property
    def is_student_user(self):
        return self.role == self.ROLE_STUDENT

    def save(self, *args, **kwargs):
        # Tự động set is_staff cho admin và manager để quản trị hệ thống
        if self.role in [self.ROLE_ADMIN, self.ROLE_MANAGER]:
            self.is_staff = True
        super().save(*args, **kwargs)


class Notification(models.Model):
    """
    Hệ thống thông báo nội bộ:
    Được sử dụng khi học viên xin miễn bài tập, giáo viên duyệt, quản lý được thông báo.
    """
    TYPE_EXEMPTION_REQUEST = 'exemption_request'
    TYPE_EXEMPTION_APPROVED = 'exemption_approved'
    TYPE_EXEMPTION_REJECTED = 'exemption_rejected'
    TYPE_SYSTEM = 'system'

    NOTIFICATION_TYPES = (
        (TYPE_EXEMPTION_REQUEST, 'Học viên xin miễn bài tập'),
        (TYPE_EXEMPTION_APPROVED, 'Giáo viên đã duyệt miễn bài tập'),
        (TYPE_EXEMPTION_REJECTED, 'Đơn miễn bài tập bị từ chối'),
        (TYPE_SYSTEM, 'Thông báo hệ thống'),
    )

    recipient = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name="Người nhận"
    )
    sender = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sent_notifications',
        verbose_name="Người gửi"
    )
    title = models.CharField(max_length=255, verbose_name="Tiêu đề")
    message = models.TextField(verbose_name="Nội dung")
    notification_type = models.CharField(
        max_length=50,
        choices=NOTIFICATION_TYPES,
        default=TYPE_SYSTEM,
        verbose_name="Loại thông báo"
    )
    is_read = models.BooleanField(default=False, verbose_name="Đã đọc")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời gian tạo")

    class Meta:
        verbose_name = "Thông báo"
        verbose_name_plural = "Thông báo"
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.get_notification_type_display()}] {self.title} -> {self.recipient.username}"

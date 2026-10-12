from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.conf import settings
from accounts.models import CustomUser


class Course(models.Model):
    """
    Mô hình Khóa học tại Trung tâm Mr Bean.
    Hỗ trợ định mức số buổi miễn BTVN:
    - 08 buổi cho TOEIC và VSTEP
    - 05 buổi cho B1
    """
    COURSE_TYPE_TOEIC = 'TOEIC'
    COURSE_TYPE_VSTEP = 'VSTEP'
    COURSE_TYPE_B1 = 'B1'
    COURSE_TYPE_OTHER = 'OTHER'

    COURSE_TYPE_CHOICES = (
        (COURSE_TYPE_TOEIC, 'TOEIC (Định mức 08 buổi miễn nghe)'),
        (COURSE_TYPE_VSTEP, 'VSTEP (Định mức 08 buổi miễn nghe)'),
        (COURSE_TYPE_B1, 'B1 (Định mức 05 buổi miễn nghe)'),
        (COURSE_TYPE_OTHER, 'Khóa học khác'),
    )

    name = models.CharField(max_length=200, verbose_name="Tên khóa học")
    code = models.CharField(max_length=50, unique=True, verbose_name="Mã khóa học")
    course_type = models.CharField(
        max_length=20,
        choices=COURSE_TYPE_CHOICES,
        default=COURSE_TYPE_TOEIC,
        verbose_name="Phân loại chương trình"
    )
    default_listening_exemption_quota = models.PositiveIntegerField(
        default=8,
        verbose_name="Định mức số buổi miễn Listening mặc định",
        help_text="Tự động gán 8 buổi cho TOEIC/VSTEP, 5 buổi cho B1"
    )
    description = models.TextField(blank=True, verbose_name="Mô tả khóa học")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Ngày tạo")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Ngày cập nhật")

    class Meta:
        verbose_name = "Khóa học"
        verbose_name_plural = "Danh sách khóa học"
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name} [{self.get_course_type_display()}]"

    def save(self, *args, **kwargs):
        # Tự động gán quota theo quy định BRD nếu không được tùy chỉnh thủ công
        if self.course_type in [self.COURSE_TYPE_TOEIC, self.COURSE_TYPE_VSTEP]:
            self.default_listening_exemption_quota = 8
        elif self.course_type == self.COURSE_TYPE_B1:
            self.default_listening_exemption_quota = 5
        super().save(*args, **kwargs)


class ClassRoom(models.Model):
    """
    Lớp học cụ thể.
    - Phân công giáo viên vào đúng lớp đang dạy để chấm bài.
    - Quản lý giao bài tập không bị nhầm lớp.
    """
    name = models.CharField(max_length=200, verbose_name="Tên lớp học")
    class_code = models.CharField(max_length=50, unique=True, verbose_name="Mã lớp")
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='classes',
        verbose_name="Thuộc khóa học"
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'role': CustomUser.ROLE_TEACHER},
        related_name='teaching_classes',
        verbose_name="Giáo viên phụ trách chấm bài"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_classes',
        verbose_name="Người tạo (Admin/Quản lý)"
    )
    start_date = models.DateField(null=True, blank=True, verbose_name="Ngày khai giảng")
    end_date = models.DateField(null=True, blank=True, verbose_name="Ngày bế giảng")
    is_active = models.BooleanField(default=True, verbose_name="Đang hoạt động")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Ngày tạo")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Ngày cập nhật")

    class Meta:
        verbose_name = "Lớp học"
        verbose_name_plural = "Danh sách lớp học"
        ordering = ['-created_at']

    def __str__(self):
        teacher_name = self.teacher.get_full_name() or self.teacher.username if self.teacher else "Chưa phân công GV"
        return f"{self.class_code} - {self.name} (GV: {teacher_name})"

    def clean(self):
        super().clean()
        if self.teacher and self.teacher.role != CustomUser.ROLE_TEACHER:
            raise ValidationError({'teacher': "Người được phân công phải có vai trò là Giáo viên/CTV."})

    @property
    def total_students(self):
        return self.enrollments.filter(status='active').count()


class Enrollment(models.Model):
    """
    Ghi danh học viên vào lớp học.
    Đảm bảo 1 học viên không bị thêm trùng lặp vào 1 lớp.
    """
    STATUS_ACTIVE = 'active'
    STATUS_COMPLETED = 'completed'
    STATUS_DROPPED = 'dropped'

    STATUS_CHOICES = (
        (STATUS_ACTIVE, 'Đang theo học'),
        (STATUS_COMPLETED, 'Đã hoàn thành'),
        (STATUS_DROPPED, 'Bảo lưu / Nghỉ học'),
    )

    classroom = models.ForeignKey(
        ClassRoom,
        on_delete=models.CASCADE,
        related_name='enrollments',
        verbose_name="Lớp học"
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={'role': CustomUser.ROLE_STUDENT},
        related_name='class_enrollments',
        verbose_name="Học viên"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE,
        verbose_name="Trạng thái học tập"
    )
    enrolled_at = models.DateTimeField(auto_now_add=True, verbose_name="Ngày vào lớp")

    class Meta:
        verbose_name = "Học viên trong lớp"
        verbose_name_plural = "Danh sách học viên trong lớp"
        unique_together = ('classroom', 'student')
        ordering = ['classroom', 'student__username']

    def __str__(self):
        return f"{self.student.username} - {self.classroom.class_code} ({self.get_status_display()})"

    def clean(self):
        super().clean()
        if self.student and self.student.role != CustomUser.ROLE_STUDENT:
            raise ValidationError({'student': "Chỉ người dùng có vai trò 'Học viên' mới được thêm vào lớp học."})


class StudentExemptionQuota(models.Model):
    """
    Cơ chế kiểm soát số buổi miễn BTVN nghe của học viên trong từng lớp:
    - 08 buổi cho TOEIC/VSTEP
    - 05 buổi cho B1
    """
    enrollment = models.OneToOneField(
        Enrollment,
        on_delete=models.CASCADE,
        related_name='exemption_quota',
        verbose_name="Học viên trong lớp"
    )
    max_quota = models.PositiveIntegerField(
        default=0,
        verbose_name="Số buổi miễn tối đa",
        help_text="Được thiết lập tự động từ loại khóa học (8 cho TOEIC/VSTEP, 5 cho B1)"
    )
    used_quota = models.PositiveIntegerField(
        default=0,
        verbose_name="Số buổi đã sử dụng"
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Cập nhật lần cuối")

    class Meta:
        verbose_name = "Hạn mức miễn BTVN"
        verbose_name_plural = "Hạn mức miễn BTVN học viên"

    def __str__(self):
        return f"{self.enrollment.student.username} ({self.enrollment.classroom.class_code}): Còn {self.remaining_quota}/{self.max_quota} buổi"

    @property
    def remaining_quota(self):
        """Số buổi miễn còn lại"""
        return max(0, self.max_quota - self.used_quota)

    @property
    def can_request_exemption(self):
        """Kiểm tra học viên còn lượt xin miễn không"""
        return self.remaining_quota > 0 and self.enrollment.status == Enrollment.STATUS_ACTIVE

    def save(self, *args, **kwargs):
        # Tự động khởi tạo max_quota theo khóa học nếu chưa được gán
        if not self.pk and self.max_quota == 0 and self.enrollment_id:
            course = self.enrollment.classroom.course
            if course.course_type in [Course.COURSE_TYPE_TOEIC, Course.COURSE_TYPE_VSTEP]:
                self.max_quota = 8
            elif course.course_type == Course.COURSE_TYPE_B1:
                self.max_quota = 5
            else:
                self.max_quota = course.default_listening_exemption_quota
        super().save(*args, **kwargs)


class ExemptionRequest(models.Model):
    """
    Đơn xin miễn bài tập về nhà của học viên.
    QUY TẮC BẮT BUỘC: CHỈ MIỄN BÀI TẬP NGHE (LISTENING).
    """
    HOMEWORK_TYPE_LISTENING = 'listening'
    HOMEWORK_TYPE_VOCABULARY = 'vocabulary'
    HOMEWORK_TYPE_SPEAKING = 'speaking'

    HOMEWORK_TYPE_CHOICES = (
        (HOMEWORK_TYPE_LISTENING, 'Bài tập Nghe (Listening) - [Được áp dụng miễn]'),
        (HOMEWORK_TYPE_VOCABULARY, 'Bài tập Từ vựng - [Không được miễn]'),
        (HOMEWORK_TYPE_SPEAKING, 'Bài tập Nói (Ghi âm) - [Không được miễn]'),
    )

    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'

    STATUS_CHOICES = (
        (STATUS_PENDING, 'Chờ duyệt'),
        (STATUS_APPROVED, 'Đã chấp thuận miễn'),
        (STATUS_REJECTED, 'Đã từ chối'),
    )

    enrollment = models.ForeignKey(
        Enrollment,
        on_delete=models.CASCADE,
        related_name='exemption_requests',
        verbose_name="Học viên lớp"
    )
    homework_type = models.CharField(
        max_length=20,
        choices=HOMEWORK_TYPE_CHOICES,
        default=HOMEWORK_TYPE_LISTENING,
        verbose_name="Loại bài tập"
    )
    session_title = models.CharField(
        max_length=255,
        verbose_name="Buổi học / Bài tập xin miễn",
        help_text="Ví dụ: Buổi 4 - Listening Part 2"
    )
    reason = models.TextField(verbose_name="Lý do xin miễn")
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        verbose_name="Trạng thái duyệt"
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_exemptions',
        verbose_name="Giáo viên duyệt"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="Thời gian duyệt")
    review_note = models.TextField(blank=True, null=True, verbose_name="Ghi chú của giáo viên")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời gian gửi đơn")

    class Meta:
        verbose_name = "Đơn xin miễn BTVN"
        verbose_name_plural = "Danh sách đơn xin miễn BTVN"
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.get_status_display()}] {self.enrollment.student.username} - {self.session_title}"

    def clean(self):
        super().clean()
        # 1. QUY TẮC CỐT LÕI: CHỈ ĐƯỢC PHÉP MIỄN BÀI TẬP NGHE (LISTENING)
        if self.homework_type != self.HOMEWORK_TYPE_LISTENING:
            raise ValidationError({
                'homework_type': (
                    "Quy định trung tâm Mr Bean: CHỈ MIỄN BÀI TẬP NGHE (LISTENING)! "
                    "Học viên bắt buộc phải hoàn thành bài tập Từ vựng và Nói (ghi âm trực tiếp)."
                )
            })

        # 2. Kiểm tra hạn mức còn lại khi tạo đơn mới
        if not self.pk or self.status == self.STATUS_PENDING:
            from django.core.exceptions import ObjectDoesNotExist
            try:
                enrollment = self.enrollment
            except ObjectDoesNotExist:
                enrollment = None

            if enrollment:
                quota = getattr(enrollment, 'exemption_quota', None)
                if quota and quota.remaining_quota <= 0:
                    raise ValidationError(
                        f"Học viên đã sử dụng hết số buổi miễn BTVN ({quota.used_quota}/{quota.max_quota} buổi) của khóa học này."
                    )

    def approve(self, teacher_user, note=""):
        """
        Nghiệp vụ giáo viên duyệt miễn bài tập:
        1. Kiểm tra quyền (phải là giáo viên phụ trách lớp hoặc Admin).
        2. Kiểm tra hạn mức còn lại.
        3. Tăng used_quota lên 1.
        4. Gửi thông báo đến Quản lý (Manager) và Học viên (Student).
        """
        from accounts.models import Notification

        classroom = self.enrollment.classroom

        # Xác thực quyền: Giáo viên của lớp hoặc Admin
        if not (teacher_user.is_superuser or teacher_user.role == CustomUser.ROLE_ADMIN or classroom.teacher_id == teacher_user.id):
            raise ValidationError("Chỉ giáo viên phụ trách lớp này hoặc Admin mới có quyền duyệt miễn bài tập.")

        quota, _ = StudentExemptionQuota.objects.get_or_create(enrollment=self.enrollment)
        if quota.remaining_quota <= 0:
            raise ValidationError(f"Học viên đã hết hạn mức miễn bài tập ({quota.used_quota}/{quota.max_quota}).")

        # Cập nhật quota và trạng thái đơn
        quota.used_quota += 1
        quota.save()

        self.status = self.STATUS_APPROVED
        self.reviewed_by = teacher_user
        self.reviewed_at = timezone.now()
        self.review_note = note
        self.save()

        # 1. Thông báo cho Quản lý (Manager) về buổi xin miễn đã được duyệt
        managers = CustomUser.objects.filter(role=CustomUser.ROLE_MANAGER, is_active=True)
        teacher_display = teacher_user.get_full_name() or teacher_user.username
        student_display = self.enrollment.student.get_full_name() or self.enrollment.student.username

        for mgr in managers:
            Notification.objects.create(
                recipient=mgr,
                sender=teacher_user,
                title=f"Học viên được miễn BTVN Nghe: {student_display} ({classroom.class_code})",
                message=(
                    f"Giáo viên {teacher_display} đã DUYỆT đơn xin miễn BTVN Nghe cho học viên {student_display}.\n"
                    f"- Lớp: {classroom.name} ({classroom.class_code})\n"
                    f"- Bài tập / Buổi: {self.session_title}\n"
                    f"- Lý do: {self.reason}\n"
                    f"- Hạn mức còn lại: {quota.remaining_quota}/{quota.max_quota} buổi."
                ),
                notification_type=Notification.TYPE_EXEMPTION_APPROVED
            )

        # 2. Thông báo cho Học viên
        Notification.objects.create(
            recipient=self.enrollment.student,
            sender=teacher_user,
            title=f"Đơn xin miễn BTVN Nghe đã được duyệt: {self.session_title}",
            message=(
                f"Giáo viên {teacher_display} đã chấp thuận đơn xin miễn BTVN Nghe của bạn.\n"
                f"- Số buổi miễn còn lại của bạn trong khóa này: {quota.remaining_quota}/{quota.max_quota} buổi."
            ),
            notification_type=Notification.TYPE_EXEMPTION_APPROVED
        )

    def reject(self, teacher_user, reason):
        """
        Giáo viên từ chối đơn xin miễn:
        - Không trừ quota.
        - Gửi thông báo đến học viên kèm lý do.
        """
        from accounts.models import Notification

        classroom = self.enrollment.classroom
        if not (teacher_user.is_superuser or teacher_user.role == CustomUser.ROLE_ADMIN or classroom.teacher_id == teacher_user.id):
            raise ValidationError("Chỉ giáo viên phụ trách lớp này hoặc Admin mới có quyền từ chối đơn.")

        self.status = self.STATUS_REJECTED
        self.reviewed_by = teacher_user
        self.reviewed_at = timezone.now()
        self.review_note = reason
        self.save()

        teacher_display = teacher_user.get_full_name() or teacher_user.username
        Notification.objects.create(
            recipient=self.enrollment.student,
            sender=teacher_user,
            title=f"Đơn xin miễn BTVN Nghe bị từ chối: {self.session_title}",
            message=f"Giáo viên {teacher_display} đã từ chối đơn xin miễn BTVN của bạn.\nLý do: {reason}",
            notification_type=Notification.TYPE_EXEMPTION_REJECTED
        )

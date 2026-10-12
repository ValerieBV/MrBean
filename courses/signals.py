from django.db.models.signals import post_save
from django.dispatch import receiver
from courses.models import Enrollment, StudentExemptionQuota, ExemptionRequest, Course
from accounts.models import Notification, CustomUser


@receiver(post_save, sender=Enrollment)
def auto_create_student_exemption_quota(sender, instance, created, **kwargs):
    """
    Tự động cấp hạn mức miễn BTVN Nghe khi học viên được thêm vào lớp học:
    - 08 buổi cho TOEIC và VSTEP
    - 05 buổi cho B1
    - Khóa khác: theo default của Course
    """
    if created:
        course = instance.classroom.course
        if course.course_type in [Course.COURSE_TYPE_TOEIC, Course.COURSE_TYPE_VSTEP]:
            quota_val = 8
        elif course.course_type == Course.COURSE_TYPE_B1:
            quota_val = 5
        else:
            quota_val = course.default_listening_exemption_quota

        StudentExemptionQuota.objects.get_or_create(
            enrollment=instance,
            defaults={'max_quota': quota_val, 'used_quota': 0}
        )


@receiver(post_save, sender=ExemptionRequest)
def notify_on_exemption_request_created(sender, instance, created, **kwargs):
    """
    Khi học viên nộp đơn xin miễn, gửi thông báo ngay cho Giáo viên phụ trách lớp và Quản lý.
    """
    if created and instance.status == ExemptionRequest.STATUS_PENDING:
        classroom = instance.enrollment.classroom
        student = instance.enrollment.student
        student_name = student.get_full_name() or student.username

        # 1. Gửi cho Giáo viên phụ trách lớp để vào chấm/duyệt
        if classroom.teacher:
            Notification.objects.create(
                recipient=classroom.teacher,
                sender=student,
                title=f"Đơn xin miễn BTVN Nghe mới: {student_name} ({classroom.class_code})",
                message=(
                    f"Học viên {student_name} thuộc lớp {classroom.name} vừa nộp đơn xin miễn BTVN Nghe.\n"
                    f"- Bài tập: {instance.session_title}\n"
                    f"- Lý do: {instance.reason}\n"
                    f"Vui lòng vào hệ thống xem xét và phê duyệt."
                ),
                notification_type=Notification.TYPE_EXEMPTION_REQUEST
            )

        # 2. Quản lý được thông báo về việc có buổi xin miễn của học viên
        managers = CustomUser.objects.filter(role=CustomUser.ROLE_MANAGER, is_active=True)
        for mgr in managers:
            Notification.objects.create(
                recipient=mgr,
                sender=student,
                title=f"[Quản lý] Học viên xin miễn BTVN: {student_name} ({classroom.class_code})",
                message=(
                    f"Học viên {student_name} (Lớp {classroom.class_code}) vừa gửi đơn xin miễn BTVN Nghe.\n"
                    f"- Bài tập: {instance.session_title}\n"
                    f"- Giáo viên phụ trách: {classroom.teacher.get_full_name() if classroom.teacher else 'Chưa có'}"
                ),
                notification_type=Notification.TYPE_EXEMPTION_REQUEST
            )

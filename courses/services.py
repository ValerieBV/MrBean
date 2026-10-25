from django.core.exceptions import ValidationError
from django.db import transaction
from courses.models import Course, ClassRoom, Enrollment, StudentExemptionQuota, ExemptionRequest
from accounts.models import CustomUser


class ClassManagementService:
    """
    Dịch vụ quản trị lớp học, phân công giáo viên và quản lý danh sách học viên.
    Đảm bảo tính toàn vẹn dữ liệu, tránh giao nhầm bài và nhầm lớp.
    """

    @staticmethod
    def assign_teacher_to_class(classroom: ClassRoom, teacher: CustomUser) -> ClassRoom:
        """
        Phân công giáo viên vào lớp học để chấm bài.
        Chỉ chấp nhận user có vai trò 'teacher'.
        """
        if teacher.role != CustomUser.ROLE_TEACHER:
            raise ValidationError(f"Người dùng '{teacher.username}' không phải là Giáo viên (vai trò hiện tại: {teacher.get_role_display()}).")
        
        classroom.teacher = teacher
        classroom.save(update_fields=['teacher', 'updated_at'])
        return classroom

    @staticmethod
    def enroll_student_to_class(classroom: ClassRoom, student: CustomUser) -> Enrollment:
        """
        Thêm học viên vào lớp học.
        Chỉ chấp nhận user có vai trò 'student'.
        Tự động kích hoạt hạn mức miễn BTVN nghe qua signal.
        """
        if student.role != CustomUser.ROLE_STUDENT:
            raise ValidationError(f"Người dùng '{student.username}' không phải là Học viên (vai trò hiện tại: {student.get_role_display()}).")

        existing_enrollment = Enrollment.objects.filter(student=student, status=Enrollment.STATUS_ACTIVE).first()
        if existing_enrollment:
            raise ValidationError(
                f"Học viên '{student.username}' đã thuộc lớp {existing_enrollment.classroom.class_code}. "
                f"Mỗi học viên chỉ được cố định tại 1 lớp duy nhất."
            )

        enrollment = Enrollment.objects.create(
            classroom=classroom,
            student=student,
            status=Enrollment.STATUS_ACTIVE
        )
        from assignments.models import ClassAssignment
        from dashboard.integration import sync_class_assignment
        from django.utils import timezone
        for assignment in ClassAssignment.objects.filter(classroom=classroom, due_at__gte=timezone.now()):
            sync_class_assignment(assignment)
        return enrollment

    @staticmethod
    def remove_student_from_class(classroom: ClassRoom, student: CustomUser) -> bool:
        """
        Xóa học viên khỏi lớp học (chuyển trạng thái dropped hoặc xóa ghi danh).
        """
        enrollment = Enrollment.objects.filter(classroom=classroom, student=student).first()
        if not enrollment:
            raise ValidationError(f"Học viên '{student.username}' không có trong lớp {classroom.class_code}.")
        
        enrollment.status = Enrollment.STATUS_DROPPED
        enrollment.save(update_fields=['status'])
        return True


class ExemptionControlService:
    """
    Dịch vụ kiểm soát số buổi miễn Bài tập về nhà (BTVN):
    - Hạn mức theo mã học viên (T/V: 8 buổi, B: 5 buổi).
    - Nghiệp vụ: Bắt buộc làm Listening. CHỈ CHO PHÉP MIỄN SPEAKING VÀ VOCABULARY.
    - Thông báo đến Quản lý và Học viên khi duyệt.
    """

    @staticmethod
    @transaction.atomic
    def submit_exemption(
        student: CustomUser,
        classroom: ClassRoom,
        homework_type: str,
        session_title: str,
        reason: str
    ) -> ExemptionRequest:
        """
        Học viên nộp đơn xin miễn BTVN (Speaking hoặc Vocabulary).
        Bắt buộc làm Listening (hệ thống từ chối miễn Listening).
        Tự động kiểm tra:
        1. Loại bài tập không phải Listening.
        2. Học viên có đang học lớp này không.
        3. Hạn mức còn lại có > 0 không.
        """
        if homework_type == ExemptionRequest.HOMEWORK_TYPE_LISTENING:
            raise ValidationError(
                "Bài tập Nghe (Listening) là BẮT BUỘC đối với mọi học viên. "
                "Hệ thống chỉ cho phép xin miễn bài tập Nói (Speaking) hoặc Từ vựng (Vocabulary)."
            )

        enrollment = Enrollment.objects.filter(
            classroom=classroom,
            student=student,
            status=Enrollment.STATUS_ACTIVE
        ).first()

        if not enrollment:
            raise ValidationError(f"Học viên {student.username} không có lớp học active tại lớp {classroom.class_code}.")

        quota, _ = StudentExemptionQuota.objects.get_or_create(enrollment=enrollment)
        if quota.remaining_quota <= 0:
            raise ValidationError(
                f"Bạn đã sử dụng hết số buổi miễn BTVN ({quota.used_quota}/{quota.max_quota} buổi)."
            )

        # Kiểm tra xem đã nộp đơn cho buổi này và loại bài tập này đang chờ duyệt chưa
        if ExemptionRequest.objects.filter(
            enrollment=enrollment,
            homework_type=homework_type,
            session_title=session_title,
            status=ExemptionRequest.STATUS_PENDING
        ).exists():
            raise ValidationError(f"Bạn đã có đơn xin miễn cho bài tập '{session_title}' đang chờ duyệt.")

        exemption_req = ExemptionRequest(
            enrollment=enrollment,
            homework_type=homework_type,
            session_title=session_title,
            reason=reason,
            status=ExemptionRequest.STATUS_PENDING
        )
        exemption_req.full_clean()
        exemption_req.save()
        return exemption_req

    @staticmethod
    def submit_listening_exemption(student, classroom, session_title, reason):
        """Deprecated: Giữ để tương thích ngược nếu còn lời gọi cũ."""
        raise ValidationError("Bài tập Nghe (Listening) là bắt buộc, không được phép xin miễn.")

    @staticmethod
    def approve_exemption(exemption_id: int, teacher: CustomUser, note: str = "") -> ExemptionRequest:
        """
        Giáo viên duyệt đơn miễn BTVN.
        """
        exemption_req = ExemptionRequest.objects.select_related(
            'enrollment__classroom', 'enrollment__student', 'enrollment__exemption_quota'
        ).get(id=exemption_id)

        exemption_req.approve(teacher_user=teacher, note=note)
        return exemption_req

    @staticmethod
    def reject_exemption(exemption_id: int, teacher: CustomUser, reason: str) -> ExemptionRequest:
        """
        Giáo viên từ chối đơn miễn BTVN.
        """
        exemption_req = ExemptionRequest.objects.select_related(
            'enrollment__classroom', 'enrollment__student'
        ).get(id=exemption_id)

        exemption_req.reject(teacher_user=teacher, reason=reason)
        return exemption_req

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.urls import reverse
from .models import Course, ClassRoom, Enrollment, StudentExemptionQuota, ExemptionRequest
from accounts.models import CustomUser
from accounts.notifications import notify


class ClassManagementService:
    @staticmethod
    def assign_teacher_to_class(classroom, teacher):
        if teacher.role != 'teacher' or not teacher.is_active:
            raise ValidationError('Người được phân công phải là giáo viên đang hoạt động.')
        classroom.teacher = teacher
        classroom.save(update_fields=['teacher', 'updated_at'])
        from dashboard.integration import sync_class_assignment
        for assignment in classroom.assignments.all():
            sync_class_assignment(assignment)
        return classroom

    @staticmethod
    @transaction.atomic
    def enroll_student_to_class(classroom, student):
        student = CustomUser.objects.select_for_update().get(pk=student.pk)
        if student.role != 'student' or not student.is_active:
            raise ValidationError('Chỉ ghi danh tài khoản học viên đang hoạt động.')
        if not classroom.is_active:
            raise ValidationError('Lớp đã ngừng hoạt động.')
        if Enrollment.objects.filter(student=student, status='active').exists():
            raise ValidationError('Học viên cố định tại 1 lớp duy nhất đang hoạt động.')
        enrollment, _ = Enrollment.objects.update_or_create(classroom=classroom, student=student, defaults={'status':'active'})
        from dashboard.integration import sync_class_assignment
        for assignment in classroom.assignments.filter(is_active=True, due_at__gte=timezone.now()):
            sync_class_assignment(assignment)
        return enrollment

    @staticmethod
    @transaction.atomic
    def remove_student_from_class(classroom, student):
        enrollment = Enrollment.objects.select_for_update().filter(classroom=classroom, student=student).first()
        if not enrollment:
            raise ValidationError('Học viên không thuộc lớp này.')
        enrollment.status = 'dropped'
        enrollment.save(update_fields=['status'])
        notify(recipient=student, title='Cập nhật ghi danh lớp '+classroom.class_code,
            message='Ghi danh đã ngừng hoạt động. Bạn vẫn xem được lịch sử kết quả của mình.',
            target_url=reverse('dashboard:index'))
        return True


class ExemptionControlService:
    @staticmethod
    @transaction.atomic
    def submit_exemption(student, classroom, homework_type=None, session_title='', reason='', assignment=None):
        if assignment:
            homework_type, session_title = assignment.lesson.skill, assignment.lesson.title
        if homework_type == 'listening':
            raise ValidationError('Bài tập Listening là BẮT BUỘC; chỉ miễn Speaking và Vocabulary.')
        if homework_type not in ('speaking','vocabulary'):
            raise ValidationError('Loại bài xin miễn không hợp lệ.')
        if not reason.strip() or len(reason)>5000:
            raise ValidationError('Nhập lý do từ 1 đến 5.000 ký tự.')
        enrollment = Enrollment.objects.select_for_update().filter(student=student, classroom=classroom, status='active').first()
        if not enrollment or not classroom.is_active:
            raise ValidationError('Học viên cần ghi danh hoạt động trong lớp này.')
        quota, _ = StudentExemptionQuota.objects.get_or_create(enrollment=enrollment)
        if quota.remaining_quota <= 0:
            raise ValidationError('Bạn đã hết số buổi miễn bài tập.')
        if assignment:
            from dashboard.models import LearningTask
            task = LearningTask.objects.select_for_update().filter(assignment=assignment, learner=student).first()
            if assignment.classroom_id != classroom.pk or not assignment.is_active or assignment.assigned_at > timezone.now() or not task:
                raise ValidationError('Bài tập chưa được giao hoặc không thuộc lớp này.')
            if task.jobs.exists() or task.exemption_id:
                raise ValidationError('Chỉ có thể xin miễn bài chưa nộp và chưa được miễn.')
            if ExemptionRequest.objects.filter(enrollment=enrollment, assignment=assignment, status__in=['pending','approved']).exists():
                raise ValidationError('Bài này đã có đơn đang chờ hoặc đã được miễn.')
        elif ExemptionRequest.objects.filter(enrollment=enrollment, homework_type=homework_type,
                session_title=session_title, status='pending').exists():
            raise ValidationError('Đã có đơn đang chờ cho buổi này.')
        # Text-only requests remain readable/importable for the source branch's legacy data.
        request = ExemptionRequest(enrollment=enrollment, homework_type=homework_type,
            session_title=session_title, assignment=assignment, reason=reason.strip())
        request.full_clean()
        request.save()
        return request

    @staticmethod
    def submit_listening_exemption(student, classroom, session_title, reason):
        raise ValidationError('Listening là bắt buộc, không được miễn.')

    @staticmethod
    @transaction.atomic
    def review(exemption_id, teacher, *, approve, note='', assignment=None):
        request = ExemptionRequest.objects.select_for_update().select_related('enrollment__classroom',
            'enrollment__student', 'assignment__lesson').get(pk=exemption_id)
        classroom = request.enrollment.classroom
        if not (teacher.is_superuser or teacher.role == 'admin' or (teacher.role=='teacher' and classroom.teacher_id==teacher.pk)):
            raise ValidationError('Chỉ giáo viên phụ trách lớp hoặc admin được duyệt.')
        if request.status != 'pending':
            raise ValidationError('Đơn này đã được xử lý, không cập nhật hạn mức lần nữa.')
        if request.homework_type == 'listening':
            raise ValidationError('Listening là bắt buộc, không được duyệt miễn.')
        if assignment:
            if request.assignment_id and request.assignment_id != assignment.pk:
                raise ValidationError('Không đổi bài của đơn đã liên kết.')
            if assignment.classroom_id != classroom.pk or assignment.lesson.skill != request.homework_type:
                raise ValidationError('Bài liên kết cần đúng lớp và kỹ năng.')
            request.assignment, request.session_title = assignment, assignment.lesson.title
        if not approve and not note.strip():
            raise ValidationError('Cần nhập lý do từ chối.')
        if approve:
            if request.enrollment.status != 'active':
                raise ValidationError('Học viên đã ngừng ghi danh.')
            quota = StudentExemptionQuota.objects.select_for_update().get(enrollment=request.enrollment)
            if quota.remaining_quota <= 0:
                raise ValidationError('Học viên đã hết hạn mức miễn bài.')
            task = None
            if request.assignment_id:
                from dashboard.models import LearningTask
                task = LearningTask.objects.select_for_update().filter(assignment=request.assignment,
                    learner_id=request.enrollment.student_id).first()
                if not task or task.jobs.exists() or task.exemption_id or not request.assignment.is_active:
                    raise ValidationError('Bài đã nộp, đã được miễn hoặc ngừng nhận bài.')
            quota.used_quota += 1
            quota.save()
            if task:
                task.exemption = request
                task.save(update_fields=['exemption'])
        request.status = 'approved' if approve else 'rejected'
        request.reviewed_by, request.reviewed_at, request.review_note = teacher, timezone.now(), note.strip()
        request.save()
        url = reverse('courses:exemption_list')
        label = 'được chấp thuận' if approve else 'bị từ chối'
        notify(recipient=request.enrollment.student, sender=teacher,
            title='Đơn miễn bài '+label, message=request.session_title+'. '+note.strip(), target_url=url,
            kind='exemption_approved' if approve else 'exemption_rejected', event_key=f'exemption:{request.pk}:student')
        if approve:
            for manager in CustomUser.objects.filter(role='manager', is_active=True):
                notify(recipient=manager, sender=teacher, title='Đã duyệt miễn bài '+request.session_title,
                    message=request.enrollment.student.get_full_name() or request.enrollment.student.username,
                    target_url=url, kind='exemption_approved', event_key=f'exemption:{request.pk}:manager:{manager.pk}')
        return request

    @staticmethod
    def approve_exemption(exemption_id, teacher, note='', assignment=None):
        return ExemptionControlService.review(exemption_id, teacher, approve=True, note=note, assignment=assignment)

    @staticmethod
    def reject_exemption(exemption_id, teacher, reason):
        return ExemptionControlService.review(exemption_id, teacher, approve=False, note=reason)

    @staticmethod
    @transaction.atomic
    def cancel(exemption_id, student):
        request = ExemptionRequest.objects.select_for_update().get(pk=exemption_id, enrollment__student=student)
        if request.status != 'pending':
            raise ValidationError('Chỉ hủy đơn đang chờ duyệt.')
        request.status = 'cancelled'
        request.save(update_fields=['status'])
        return request

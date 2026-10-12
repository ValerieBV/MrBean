from django.test import TestCase
from django.core.exceptions import ValidationError
from accounts.models import CustomUser, Notification
from courses.models import Course, ClassRoom, Enrollment, StudentExemptionQuota, ExemptionRequest
from courses.services import ClassManagementService, ExemptionControlService


class CourseAndExemptionTests(TestCase):
    def setUp(self):
        # 1. Tạo các loại tài khoản
        self.admin = CustomUser.objects.create_user(
            username='admin_boss', password='password123', role=CustomUser.ROLE_ADMIN
        )
        self.manager = CustomUser.objects.create_user(
            username='manager_alice', password='password123', role=CustomUser.ROLE_MANAGER
        )
        self.teacher_toeic = CustomUser.objects.create_user(
            username='teacher_bob', password='password123', role=CustomUser.ROLE_TEACHER
        )
        self.teacher_other = CustomUser.objects.create_user(
            username='teacher_charlie', password='password123', role=CustomUser.ROLE_TEACHER
        )
        self.student_toeic = CustomUser.objects.create_user(
            username='student_david', password='password123', role=CustomUser.ROLE_STUDENT
        )
        self.student_b1 = CustomUser.objects.create_user(
            username='student_emma', password='password123', role=CustomUser.ROLE_STUDENT
        )

        # 2. Tạo khóa học TOEIC và B1
        self.course_toeic = Course.objects.create(
            name='TOEIC Luyện thi Cấp Tốc',
            code='TOEIC-INT',
            course_type=Course.COURSE_TYPE_TOEIC
        )
        self.course_vstep = Course.objects.create(
            name='VSTEP B2 Chinh Phục',
            code='VSTEP-B2',
            course_type=Course.COURSE_TYPE_VSTEP
        )
        self.course_b1 = Course.objects.create(
            name='Tiếng Anh Chuẩn B1',
            code='ENG-B1',
            course_type=Course.COURSE_TYPE_B1
        )

        # 3. Tạo lớp học
        self.class_toeic = ClassRoom.objects.create(
            name='Lớp TOEIC 600+ Tối 2-4-6',
            class_code='TOEIC-2401',
            course=self.course_toeic,
            teacher=self.teacher_toeic,
            created_by=self.manager
        )
        self.class_b1 = ClassRoom.objects.create(
            name='Lớp B1 Chiều T7-CN',
            class_code='B1-2401',
            course=self.course_b1,
            teacher=self.teacher_other,
            created_by=self.manager
        )

    def test_default_course_quota_rules(self):
        """Kiểm tra định mức 8 buổi cho TOEIC/VSTEP và 5 buổi cho B1"""
        self.assertEqual(self.course_toeic.default_listening_exemption_quota, 8)
        self.assertEqual(self.course_vstep.default_listening_exemption_quota, 8)
        self.assertEqual(self.course_b1.default_listening_exemption_quota, 5)

    def test_enrollment_and_auto_quota_assignment(self):
        """Kiểm tra tự động cấp quota khi thêm học viên vào lớp"""
        # Thêm học viên vào lớp TOEIC -> nhận 8 buổi miễn
        enrollment_toeic = ClassManagementService.enroll_student_to_class(self.class_toeic, self.student_toeic)
        self.assertEqual(enrollment_toeic.exemption_quota.max_quota, 8)
        self.assertEqual(enrollment_toeic.exemption_quota.used_quota, 0)
        self.assertEqual(enrollment_toeic.exemption_quota.remaining_quota, 8)

        # Thêm học viên vào lớp B1 -> nhận 5 buổi miễn
        enrollment_b1 = ClassManagementService.enroll_student_to_class(self.class_b1, self.student_b1)
        self.assertEqual(enrollment_b1.exemption_quota.max_quota, 5)
        self.assertEqual(enrollment_b1.exemption_quota.used_quota, 0)
        self.assertEqual(enrollment_b1.exemption_quota.remaining_quota, 5)

    def test_cannot_enroll_teacher_as_student(self):
        """Không được phép thêm giáo viên làm học viên trong lớp"""
        with self.assertRaises(ValidationError):
            ClassManagementService.enroll_student_to_class(self.class_toeic, self.teacher_other)

    def test_cannot_assign_student_as_teacher(self):
        """Không được phép phân công học viên làm giáo viên phụ trách lớp"""
        with self.assertRaises(ValidationError):
            ClassManagementService.assign_teacher_to_class(self.class_toeic, self.student_toeic)

    def test_only_listening_exemption_allowed(self):
        """QUY TẮC CỐT LÕI: Chỉ cho phép miễn bài tập Nghe (Listening), chặn Từ vựng và Nói"""
        enrollment = ClassManagementService.enroll_student_to_class(self.class_toeic, self.student_toeic)

        # 1. Thử xin miễn bài tập Từ vựng -> Bị chặn
        with self.assertRaises(ValidationError) as ctx:
            req_vocab = ExemptionRequest(
                enrollment=enrollment,
                homework_type=ExemptionRequest.HOMEWORK_TYPE_VOCABULARY,
                session_title='Buổi 2 - Từ vựng chủ đề Kinh Tế',
                reason='Bận công tác'
            )
            req_vocab.full_clean()
        self.assertIn('CHỈ MIỄN BÀI TẬP NGHE', str(ctx.exception))

        # 2. Thử xin miễn bài tập Nói (Ghi âm) -> Bị chặn
        with self.assertRaises(ValidationError) as ctx:
            req_speaking = ExemptionRequest(
                enrollment=enrollment,
                homework_type=ExemptionRequest.HOMEWORK_TYPE_SPEAKING,
                session_title='Buổi 3 - Ghi âm Part 1',
                reason='Bị viêm họng'
            )
            req_speaking.full_clean()
        self.assertIn('CHỈ MIỄN BÀI TẬP NGHE', str(ctx.exception))

        # 3. Xin miễn bài tập Nghe (Listening) -> Hợp lệ và thành công
        req_listening = ExemptionRequest(
            enrollment=enrollment,
            homework_type=ExemptionRequest.HOMEWORK_TYPE_LISTENING,
            session_title='Buổi 4 - Listening Part 2',
            reason='Đi công tác đột xuất'
        )
        req_listening.full_clean()
        req_listening.save()
        self.assertEqual(req_listening.status, ExemptionRequest.STATUS_PENDING)

    def test_approval_workflow_decrements_quota_and_notifies_manager(self):
        """
        Quy trình duyệt:
        - Đúng giáo viên của lớp duyệt.
        - Trừ hạn mức (used_quota tăng 1, remaining_quota giảm 1).
        - Quản lý (manager) nhận được thông báo.
        """
        enrollment = ClassManagementService.enroll_student_to_class(self.class_toeic, self.student_toeic)
        
        # Học viên nộp đơn xin miễn bài nghe
        req = ExemptionControlService.submit_listening_exemption(
            student=self.student_toeic,
            classroom=self.class_toeic,
            session_title='Buổi 5 - Listening Part 3',
            reason='Trùng lịch thi trường đại học'
        )

        # Giáo viên lớp khác (teacher_other) cố tình duyệt -> BỊ TỪ CHỐI
        with self.assertRaises(ValidationError):
            req.approve(teacher_user=self.teacher_other)

        # Đúng giáo viên phụ trách lớp (teacher_bob) duyệt -> THÀNH CÔNG
        req.approve(teacher_user=self.teacher_toeic, note="Đồng ý duyệt cho em")
        self.assertEqual(req.status, ExemptionRequest.STATUS_APPROVED)

        # Kiểm tra quota đã trừ
        quota = StudentExemptionQuota.objects.get(enrollment=enrollment)
        self.assertEqual(quota.used_quota, 1)
        self.assertEqual(quota.remaining_quota, 7)

        # Kiểm tra Quản lý (Manager) đã nhận được thông báo
        manager_notifications = Notification.objects.filter(
            recipient=self.manager,
            notification_type=Notification.TYPE_EXEMPTION_APPROVED
        )
        self.assertTrue(manager_notifications.exists())
        self.assertIn("Học viên được miễn BTVN Nghe", manager_notifications.first().title)

    def test_cannot_exceed_maximum_quota(self):
        """Kiểm tra không thể miễn vượt quá hạn mức tối đa (ví dụ 5 buổi cho B1)"""
        enrollment = ClassManagementService.enroll_student_to_class(self.class_b1, self.student_b1)
        quota = enrollment.exemption_quota
        
        # Giả lập học viên đã dùng hết 5 buổi
        quota.used_quota = 5
        quota.save()
        self.assertEqual(quota.remaining_quota, 0)

        # Học viên cố tình gửi đơn thứ 6 -> Bị chặn ngay từ service
        with self.assertRaises(ValidationError) as ctx:
            ExemptionControlService.submit_listening_exemption(
                student=self.student_b1,
                classroom=self.class_b1,
                session_title='Buổi 6 - Listening B1 Part 1',
                reason='Xin miễn tiếp'
            )
        self.assertIn("hết số buổi miễn", str(ctx.exception))

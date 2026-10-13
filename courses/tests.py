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
        # Học viên với Mã học viên theo quy chuẩn: [T/B/V] + Khóa + Cơ sở + Tên + STT
        self.student_toeic = CustomUser.objects.create_user(
            username='student_david',
            password='password123',
            role=CustomUser.ROLE_STUDENT,
            student_code='T253C1David01'  # T -> 8 buổi
        )
        self.student_b1 = CustomUser.objects.create_user(
            username='student_emma',
            password='password123',
            role=CustomUser.ROLE_STUDENT,
            student_code='B253C1Emma02'  # B -> 5 buổi
        )
        self.student_vstep = CustomUser.objects.create_user(
            username='student_frank',
            password='password123',
            role=CustomUser.ROLE_STUDENT,
            student_code='V253C1Frank03'  # V -> 8 buổi
        )

        # 2. Tạo khóa học
        self.course_toeic = Course.objects.create(
            name='TOEIC Luyện thi Cấp Tốc',
            code='TOEIC-INT',
            course_type=Course.COURSE_TYPE_TOEIC
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

    def test_student_code_quota_parsing(self):
        """Kiểm tra bóc tách hạn mức từ ký tự đầu của Mã học viên (T/V = 8, B = 5)"""
        self.assertEqual(self.student_toeic.exemption_quota_max, 8)
        self.assertEqual(self.student_vstep.exemption_quota_max, 8)
        self.assertEqual(self.student_b1.exemption_quota_max, 5)

    def test_enrollment_and_auto_quota_assignment(self):
        """Kiểm tra tự động cấp quota theo mã học viên khi ghi danh vào lớp"""
        # Học viên mã T -> nhận 8 buổi miễn
        enrollment_toeic = ClassManagementService.enroll_student_to_class(self.class_toeic, self.student_toeic)
        self.assertEqual(enrollment_toeic.exemption_quota.max_quota, 8)
        self.assertEqual(enrollment_toeic.exemption_quota.used_quota, 0)
        self.assertEqual(enrollment_toeic.exemption_quota.remaining_quota, 8)

        # Học viên mã B -> nhận 5 buổi miễn
        enrollment_b1 = ClassManagementService.enroll_student_to_class(self.class_b1, self.student_b1)
        self.assertEqual(enrollment_b1.exemption_quota.max_quota, 5)
        self.assertEqual(enrollment_b1.exemption_quota.used_quota, 0)
        self.assertEqual(enrollment_b1.exemption_quota.remaining_quota, 5)

    def test_student_fixed_to_single_class(self):
        """Quy định: Học viên cố định tại 1 lớp duy nhất, không thể vào lớp thứ 2 khi đang active"""
        ClassManagementService.enroll_student_to_class(self.class_toeic, self.student_toeic)
        
        # Thử ghi danh vào lớp B1 khi đang học lớp TOEIC -> Bị chặn
        with self.assertRaises(ValidationError) as ctx:
            ClassManagementService.enroll_student_to_class(self.class_b1, self.student_toeic)
        self.assertIn("cố định tại 1 lớp duy nhất", str(ctx.exception))

    def test_cannot_enroll_teacher_as_student(self):
        """Không được phép thêm giáo viên làm học viên trong lớp"""
        with self.assertRaises(ValidationError):
            ClassManagementService.enroll_student_to_class(self.class_toeic, self.teacher_other)

    def test_cannot_assign_student_as_teacher(self):
        """Không được phép phân công học viên làm giáo viên phụ trách lớp"""
        with self.assertRaises(ValidationError):
            ClassManagementService.assign_teacher_to_class(self.class_toeic, self.student_toeic)

    def test_listening_is_mandatory_and_cannot_be_exempted(self):
        """QUY TẮC CỐT LÕI (ĐẢO NGƯỢC): Bắt buộc làm Listening, chỉ miễn Speaking & Vocab"""
        enrollment = ClassManagementService.enroll_student_to_class(self.class_toeic, self.student_toeic)

        # 1. Thử xin miễn bài tập Listening -> BỊ CHẶN NGAY
        with self.assertRaises(ValidationError) as ctx:
            req_listening = ExemptionRequest(
                enrollment=enrollment,
                homework_type=ExemptionRequest.HOMEWORK_TYPE_LISTENING,
                session_title='Buổi 1 - Listening Part 1',
                reason='Bận việc gia đình'
            )
            req_listening.full_clean()
        self.assertIn('BẮT BUỘC', str(ctx.exception))

        # 2. Thử xin miễn qua service -> BỊ CHẶN
        with self.assertRaises(ValidationError) as ctx:
            ExemptionControlService.submit_exemption(
                student=self.student_toeic,
                classroom=self.class_toeic,
                homework_type=ExemptionRequest.HOMEWORK_TYPE_LISTENING,
                session_title='Buổi 1 - Listening Part 1',
                reason='Bận việc gia đình'
            )
        self.assertIn('BẮT BUỘC', str(ctx.exception))

        # 3. Xin miễn Speaking -> HỢP LỆ
        req_speaking = ExemptionControlService.submit_exemption(
            student=self.student_toeic,
            classroom=self.class_toeic,
            homework_type=ExemptionRequest.HOMEWORK_TYPE_SPEAKING,
            session_title='Buổi 2 - Speaking Part 2',
            reason='Bị viêm họng cấp'
        )
        self.assertEqual(req_speaking.status, ExemptionRequest.STATUS_PENDING)

        # 4. Xin miễn Vocabulary -> HỢP LỆ
        req_vocab = ExemptionControlService.submit_exemption(
            student=self.student_toeic,
            classroom=self.class_toeic,
            homework_type=ExemptionRequest.HOMEWORK_TYPE_VOCABULARY,
            session_title='Buổi 3 - Vocab Unit 3',
            reason='Đi công tác'
        )
        self.assertEqual(req_vocab.status, ExemptionRequest.STATUS_PENDING)

    def test_approval_workflow_decrements_quota_and_notifies_manager(self):
        """
        Quy trình duyệt:
        - Đúng giáo viên của lớp duyệt.
        - Trừ hạn mức (used_quota tăng 1, remaining_quota giảm 1).
        - Quản lý (manager) nhận được thông báo.
        """
        enrollment = ClassManagementService.enroll_student_to_class(self.class_toeic, self.student_toeic)
        
        # Học viên nộp đơn xin miễn bài Speaking
        req = ExemptionControlService.submit_exemption(
            student=self.student_toeic,
            classroom=self.class_toeic,
            homework_type=ExemptionRequest.HOMEWORK_TYPE_SPEAKING,
            session_title='Buổi 5 - Speaking Part 3',
            reason='Trùng lịch thi trường đại học'
        )

        # Giáo viên lớp khác cố tình duyệt -> BỊ TỪ CHỐI
        with self.assertRaises(ValidationError):
            req.approve(teacher_user=self.teacher_other)

        # Đúng giáo viên phụ trách lớp duyệt -> THÀNH CÔNG
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

    def test_teacher_cannot_approve_listening_exemption(self):
        """Giáo viên không thể duyệt nếu học viên xin miễn Listening"""
        enrollment = ClassManagementService.enroll_student_to_class(self.class_toeic, self.student_toeic)
        # Giả lập bản ghi listening tồn tại trong DB (lách qua save trực tiếp)
        req_listening = ExemptionRequest.objects.create(
            enrollment=enrollment,
            homework_type=ExemptionRequest.HOMEWORK_TYPE_LISTENING,
            session_title='Buổi Lạ - Listening',
            reason='Thử nghiệm',
            status=ExemptionRequest.STATUS_PENDING
        )
        with self.assertRaises(ValidationError) as ctx:
            req_listening.approve(teacher_user=self.teacher_toeic)
        self.assertIn("Listening là bắt buộc", str(ctx.exception))

    def test_cannot_exceed_maximum_quota(self):
        """Kiểm tra không thể miễn vượt quá hạn mức tối đa (5 buổi cho mã B)"""
        enrollment = ClassManagementService.enroll_student_to_class(self.class_b1, self.student_b1)
        quota = enrollment.exemption_quota
        
        # Giả lập học viên đã dùng hết 5 buổi
        quota.used_quota = 5
        quota.save()
        self.assertEqual(quota.remaining_quota, 0)

        # Học viên cố tình gửi đơn thứ 6 -> Bị chặn ngay từ service
        with self.assertRaises(ValidationError) as ctx:
            ExemptionControlService.submit_exemption(
                student=self.student_b1,
                classroom=self.class_b1,
                homework_type=ExemptionRequest.HOMEWORK_TYPE_SPEAKING,
                session_title='Buổi 6 - Speaking Practice',
                reason='Xin miễn tiếp'
            )
        self.assertIn("hết số buổi miễn", str(ctx.exception))

    def test_student_submit_exemption_view_post(self):
        """Kiểm tra học viên gửi đơn qua Web View cho Speaking thành công"""
        ClassManagementService.enroll_student_to_class(self.class_toeic, self.student_toeic)
        self.client.force_login(self.student_toeic)

        response = self.client.post(f"/courses/classes/{self.class_toeic.id}/request-exemption/", {
            'homework_type': ExemptionRequest.HOMEWORK_TYPE_SPEAKING,
            'session_title': 'Buổi 1 - Speaking Practice',
            'reason': 'Em bị ốm sốt'
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            ExemptionRequest.objects.filter(
                enrollment__student=self.student_toeic,
                session_title='Buổi 1 - Speaking Practice'
            ).exists()
        )

    def test_manager_can_create_student_account(self):
        """Kiểm tra Quản lý có quyền tạo tài khoản cho học viên kèm mã học viên"""
        self.client.force_login(self.manager)

        response = self.client.post("/accounts/users/create/", {
            'username': 'new_student_99',
            'email': 'new_student@mrbean.edu.vn',
            'first_name': 'Nguyen',
            'last_name': 'Hoc Vien',
            'role': CustomUser.ROLE_STUDENT,
            'student_code': 'T253C1Nguyen99',
            'password': 'password123',
            'confirm_password': 'password123',
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(CustomUser.objects.filter(username='new_student_99', student_code='T253C1Nguyen99').exists())

    def test_student_and_teacher_sidebar_view_restrictions(self):
        """Học viên và giáo viên khi truy cập không nhìn thấy menu QUẢN LÝ TÀI KHOẢN"""
        # 1. Học viên đăng nhập
        self.client.force_login(self.student_toeic)
        response_student = self.client.get("/courses/")
        self.assertEqual(response_student.status_code, 200)
        self.assertNotContains(response_student, ">QUẢN LÝ TÀI KHOẢN<")
        self.assertContains(response_student, "KHÓA HỌC CỦA TÔI")

        # 2. Giáo viên đăng nhập
        self.client.force_login(self.teacher_toeic)
        response_teacher = self.client.get("/courses/")
        self.assertEqual(response_teacher.status_code, 200)
        self.assertNotContains(response_teacher, ">QUẢN LÝ TÀI KHOẢN<")
        self.assertContains(response_teacher, "LỚP HỌC ĐANG DẠY")



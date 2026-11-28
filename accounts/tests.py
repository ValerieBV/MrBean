from django.test import TestCase
from accounts.models import CustomUser, Notification
from accounts.permissions import (
    can_assign_homework_to_class,
    can_grade_class_submission,
    can_approve_exemption_for_class,
)
from courses.models import Course, ClassRoom


class AccountRBACModelTest(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username='admin_user', password='password123', role=CustomUser.ROLE_ADMIN
        )
        self.manager = CustomUser.objects.create_user(
            username='manager_user', password='password123', role=CustomUser.ROLE_MANAGER
        )
        self.teacher1 = CustomUser.objects.create_user(
            username='teacher1', password='password123', role=CustomUser.ROLE_TEACHER
        )
        self.teacher2 = CustomUser.objects.create_user(
            username='teacher2', password='password123', role=CustomUser.ROLE_TEACHER
        )
        self.student = CustomUser.objects.create_user(
            username='student1', password='password123', role=CustomUser.ROLE_STUDENT
        )

        self.course = Course.objects.create(
            code='TOEIC-K1', name='TOEIC Test Prep', course_type=Course.COURSE_TYPE_TOEIC
        )
        self.classroom = ClassRoom.objects.create(
            name='TOEIC Night Class', class_code='TOEIC-N1', course=self.course, teacher=self.teacher1
        )

    def test_user_roles(self):
        self.assertTrue(self.admin.is_admin_user)
        self.assertTrue(self.manager.is_manager_user)
        self.assertTrue(self.teacher1.is_teacher_user)
        self.assertTrue(self.student.is_student_user)

    def test_can_assign_homework(self):
        # Admin và Manager có quyền giao bài cho lớp
        self.assertTrue(can_assign_homework_to_class(self.admin, self.classroom))
        self.assertTrue(can_assign_homework_to_class(self.manager, self.classroom))

        # Teacher1 là GV của lớp -> có quyền
        self.assertTrue(can_assign_homework_to_class(self.teacher1, self.classroom))

        # Teacher2 không dạy lớp này -> không có quyền giao bài
        self.assertFalse(can_assign_homework_to_class(self.teacher2, self.classroom))

        # Học viên không có quyền giao bài
        self.assertFalse(can_assign_homework_to_class(self.student, self.classroom))

    def test_can_grade_and_approve_exemption(self):
        # Admin có quyền
        self.assertTrue(can_grade_class_submission(self.admin, self.classroom))
        self.assertTrue(can_approve_exemption_for_class(self.admin, self.classroom))

        # Teacher1 phụ trách lớp -> có quyền chấm bài và duyệt miễn BTVN
        self.assertTrue(can_grade_class_submission(self.teacher1, self.classroom))
        self.assertTrue(can_approve_exemption_for_class(self.teacher1, self.classroom))

        # Teacher2 KHÔNG dạy lớp này -> KHÔNG được phép chấm bài hoặc duyệt miễn của lớp Teacher1
        self.assertFalse(can_grade_class_submission(self.teacher2, self.classroom))
        self.assertFalse(can_approve_exemption_for_class(self.teacher2, self.classroom))

    def test_notification_creation(self):
        noti = Notification.objects.create(
            recipient=self.manager,
            sender=self.teacher1,
            title='Test Notification',
            message='Học viên xin miễn bài tập',
            notification_type=Notification.TYPE_EXEMPTION_APPROVED
        )
        self.assertEqual(self.manager.notifications.count(), 1)
        self.assertFalse(noti.is_read)

    def test_student_code_and_quota_property(self):
        s_toeic = CustomUser(role=CustomUser.ROLE_STUDENT, student_code='T253C1KieuAnh01')
        s_b1 = CustomUser(role=CustomUser.ROLE_STUDENT, student_code='B253C1Minh02')
        s_vstep = CustomUser(role=CustomUser.ROLE_STUDENT, student_code='V253C1Lan03')
        s_default = CustomUser(role=CustomUser.ROLE_STUDENT, student_code='')

        self.assertEqual(s_toeic.exemption_quota_max, 8)
        self.assertEqual(s_b1.exemption_quota_max, 5)
        self.assertEqual(s_vstep.exemption_quota_max, 8)
        self.assertEqual(s_default.exemption_quota_max, 8)

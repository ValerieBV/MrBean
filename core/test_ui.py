"""Compatibility checks for source templates backed by the integrated workflow."""
import re
from django.urls import reverse
from accounts.models import Notification
from courses.models import ClassRoom
from courses.services import ExemptionControlService
from dashboard.testutils import IntegratedFixture


class ImportedUIWorkflowTests(IntegratedFixture):
    def test_sidebar_highlights_parent_section_on_child_pages(self):
        self.client.force_login(self.admin)
        enrollment = self.student.class_enrollments.get(classroom=self.classroom)
        routes = [
            ('courses:course_create', [], 'courses:course_list'),
            ('courses:course_update', [self.classroom.course_id], 'courses:course_list'),
            ('courses:assign_teacher', [self.classroom.pk], 'courses:class_list'),
            ('courses:enroll_student', [self.classroom.pk], 'courses:class_list'),
            ('courses:enrollment_update', [enrollment.pk], 'courses:class_list'),
            ('accounts:password_reset', [self.teacher.pk], 'accounts:user_list'),
            ('courses:exemption_list', [], 'courses:exemption_list'),
        ]
        for route, args, parent in routes:
            with self.subTest(route=route):
                response = self.client.get(reverse(route, args=args))
                self.assertEqual(response.status_code, 200)
                active = re.findall(r'<li class="sidebar-menu-item active"><a href="([^"]+)"', response.content.decode())
                self.assertEqual(active, [reverse(parent)])

    def test_assigned_vocabulary_never_offers_speaking_reference_link_for_staff(self):
        for actor in (self.admin, self.manager, self.teacher):
            with self.subTest(role=actor.role):
                self.client.force_login(actor)
                response = self.client.get(reverse('assignments:lesson_detail', args=[self.vocab.pk]))
                self.assertContains(response, 'Business vocabulary')
                self.assertNotContains(response, 'Cập nhật video &amp; lời mẫu')
                self.assertNotContains(response, '/reading-reference/')
                speaking = self.client.get(reverse('assignments:lesson_detail', args=[self.speaking.pk]))
                self.assertContains(speaking, reverse('assignments:reading_reference', args=[self.task.assignment_id]))

    def test_system_notifications_render_and_keep_post_actions(self):
        item = Notification.objects.create(recipient=self.student, title='Kết quả học tập',
            message='Giáo viên đã nhận bài.', target_url='/dashboard/')
        self.client.force_login(self.student)
        response = self.client.get(reverse('accounts:notification_list'))
        self.assertContains(response, 'Kết quả học tập')
        self.assertContains(response, 'Hệ thống')
        self.assertContains(response, 'method="post" action="' + reverse('accounts:notification_read', args=[item.pk]) + '"')
        item.refresh_from_db()
        self.assertFalse(item.is_read)

    def test_student_catalog_handles_missing_teacher_and_real_exemption_history(self):
        item = ExemptionControlService.submit_exemption(self.student, self.classroom,
            assignment=self.vocab_task.assignment, reason='Em xin phép nghỉ buổi này.')
        ExemptionControlService.cancel(item.pk, self.student)
        ClassRoom.objects.filter(pk=self.classroom.pk).update(teacher=None)
        self.client.force_login(self.student)
        response = self.client.get(reverse('courses:class_list'))
        self.assertContains(response, 'Chưa phân công')
        self.assertContains(response, self.vocab.title)
        self.assertContains(response, 'Đã hủy')

    def test_account_overview_displays_pending_requests_and_real_quotas(self):
        ExemptionControlService.submit_exemption(self.student, self.classroom,
            assignment=self.vocab_task.assignment, reason='Xin miễn bài từ vựng.')
        self.client.force_login(self.admin)
        response = self.client.get(reverse('accounts:user_list'))
        self.assertEqual(response.context['pending_exemptions'], 1)
        self.assertEqual(response.context['student_quotas'].paginator.count, 2)
        self.assertContains(response, self.classroom.class_code)
        self.assertContains(response, 'Còn lại:')

    def test_exemption_form_uses_assigned_work_and_shows_review_errors(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse('courses:request_exemption', args=[self.classroom.pk]))
        self.assertContains(response, 'name="assignment"')
        self.assertContains(response, self.vocab.title)
        item = ExemptionControlService.submit_exemption(self.student, self.classroom,
            assignment=self.vocab_task.assignment, reason='Xin miễn bài từ vựng.')
        self.client.force_login(self.teacher)
        response = self.client.post(reverse('courses:exemption_review', args=[item.pk]), {'action':'reject', 'note':''})
        self.assertContains(response, 'Nhập lý do từ chối')
        item.refresh_from_db()
        self.assertEqual(item.status, 'pending')

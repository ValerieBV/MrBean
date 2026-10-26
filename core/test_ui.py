"""Compatibility checks for source templates backed by the integrated workflow."""
from django.urls import reverse
from accounts.models import Notification
from courses.models import ClassRoom
from courses.services import ExemptionControlService
from dashboard.testutils import IntegratedFixture


class ImportedUIWorkflowTests(IntegratedFixture):
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

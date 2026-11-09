from datetime import timedelta
from unittest.mock import patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client
from django.urls import reverse

from accounts.models import Notification
from ai_core.models import GradingJob
from courses.models import Enrollment, ExemptionRequest
from dashboard.models import LearningTask
from dashboard.testutils import IntegratedFixture

from .models import ClassAssignment
from .services import assign_to_class, delete_class_assignment


class AssignmentDeletionTests(IntegratedFixture):
    def setUp(self):
        super().setUp()
        self.assignment = self.assignments['vocabulary']
        self.url = reverse('assignments:assigned_delete', args=[self.assignment.pk])
        self.client.force_login(self.teacher)

    def create_job(self, status='queued'):
        return GradingJob.objects.create(task=self.vocab_task, kind='vocabulary',
            submission_key='delete-test-' + status, status=status, text='Customer Deadline')

    def assert_assignment_kept(self):
        self.assertTrue(ClassAssignment.objects.filter(pk=self.assignment.pk).exists())
        self.assertTrue(LearningTask.objects.filter(pk=self.vocab_task.pk).exists())

    def test_confirmation_does_not_delete_and_shows_class_and_effect(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'Xác nhận xóa lượt giao')
        self.assertContains(response, self.vocab.title)
        self.assertContains(response, self.classroom.class_code)
        self.assertContains(response, 'csrfmiddlewaretoken')
        self.assert_assignment_kept()

    def test_staff_can_delete_and_reassign_without_changing_bank_or_other_class(self):
        other = assign_to_class(actor=self.admin, lesson=self.vocab, classroom=self.other_classroom,
            assigned_at=self.now, due_at=self.now + timedelta(days=1))
        other_task = other.tasks.get()
        for actor in (self.teacher, self.admin, self.manager):
            with self.subTest(actor=actor.role):
                self.client.force_login(actor)
                assignment_id = self.assignment.pk
                task_id = self.assignment.tasks.get().pk
                url = reverse('assignments:assigned_delete', args=[assignment_id])
                self.assertEqual(self.client.get(url).status_code, 200)
                response = self.client.post(url)
                self.assertRedirects(response, reverse('assignments:assigned_list'))
                self.assertFalse(ClassAssignment.objects.filter(pk=assignment_id).exists())
                self.assertFalse(LearningTask.objects.filter(pk=task_id).exists())
                self.assertEqual(self.vocab.words.count(), 2)
                other_task.refresh_from_db()
                self.assertEqual(other_task.assignment_id, other.pk)
                self.assignment = assign_to_class(actor=self.teacher, lesson=self.vocab,
                    classroom=self.classroom, assigned_at=self.now, due_at=self.now + timedelta(days=1))
                self.assertEqual(self.assignment.tasks.count(), 1)

    def test_deletion_removes_only_notifications_for_the_deleted_roster(self):
        event = f'assignment:{self.vocab_task.pk}'
        self.assertTrue(Notification.objects.filter(event_key=event).exists())
        other_event = f'assignment:{self.task.pk}'
        unrelated = Notification.objects.create(recipient=self.student, title='Thông báo khác',
            message='Giữ lại', event_key='unrelated-delete-test')
        self.client.post(self.url)
        self.assertFalse(Notification.objects.filter(event_key=event).exists())
        self.assertTrue(Notification.objects.filter(event_key=other_event).exists())
        self.assertTrue(Notification.objects.filter(pk=unrelated.pk).exists())

    def test_other_teacher_and_student_cannot_view_or_post_delete(self):
        for actor, status in ((self.other_teacher, 404), (self.student, 403)):
            for method in ('get', 'post'):
                with self.subTest(actor=actor.role, method=method):
                    self.client.force_login(actor)
                    self.assertEqual(getattr(self.client, method)(self.url).status_code, status)
                    self.assert_assignment_kept()

    def test_anonymous_request_requires_login(self):
        self.client.logout()
        for method in ('get', 'post'):
            response = getattr(self.client, method)(self.url)
            self.assertEqual(response.status_code, 302)
            self.assertIn(reverse('accounts:login'), response.url)
            self.assert_assignment_kept()

    def test_other_http_methods_cannot_delete(self):
        for method in ('put', 'patch', 'delete'):
            self.assertEqual(getattr(self.client, method)(self.url).status_code, 405)
            self.assert_assignment_kept()

    def test_csrf_is_required_for_confirmation(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.teacher)
        client.get(self.url)
        self.assertEqual(client.post(self.url).status_code, 403)
        self.assert_assignment_kept()
        token = client.cookies['csrftoken'].value
        self.assertRedirects(client.post(self.url, HTTP_X_CSRFTOKEN=token),
            reverse('assignments:assigned_list'))

    def test_any_submission_status_blocks_deletion_and_preserves_results(self):
        for status in GradingJob.Status.values:
            with self.subTest(status=status):
                job = self.create_job(status)
                response = self.client.get(self.url)
                self.assertContains(response, 'đã có bài nộp')
                self.assertNotContains(response, 'Xác nhận xóa lượt giao')
                self.assertContains(response, reverse('assignments:assigned_update', args=[self.assignment.pk]))
                self.assertRedirects(self.client.post(self.url), self.url)
                self.assert_assignment_kept()
                job.refresh_from_db()
                self.assertEqual(job.status, status)
                job.delete()

    def test_exemption_history_blocks_deletion_in_every_state(self):
        enrollment = Enrollment.objects.get(classroom=self.classroom, student=self.student)
        for status, _ in ExemptionRequest.STATUS_CHOICES:
            with self.subTest(status=status):
                exemption = ExemptionRequest.objects.create(enrollment=enrollment,
                    assignment=self.assignment, homework_type='vocabulary', session_title=self.vocab.title,
                    reason='Lý do kiểm thử', status=status)
                self.assertContains(self.client.get(self.url), 'đã có đơn xin miễn')
                self.assertRedirects(self.client.post(self.url), self.url)
                self.assert_assignment_kept()
                exemption.refresh_from_db()
                self.assertEqual(exemption.status, status)
                exemption.delete()

    def test_submission_after_confirmation_is_rechecked_on_post(self):
        self.assertContains(self.client.get(self.url), 'Xác nhận xóa lượt giao')
        job = self.create_job()
        self.assertRedirects(self.client.post(self.url), self.url)
        self.assert_assignment_kept()
        job.refresh_from_db()

    def test_protected_history_rolls_back_if_application_check_misses_it(self):
        job = self.create_job()
        with patch('assignments.services.assignment_delete_block_reason', return_value=''):
            with self.assertRaisesMessage(ValidationError, 'phát sinh dữ liệu liên quan'):
                delete_class_assignment(actor=self.teacher, assignment=self.assignment)
        self.assert_assignment_kept()
        job.refresh_from_db()
        self.assertTrue(Notification.objects.filter(event_key=f'assignment:{self.vocab_task.pk}').exists())

    def test_service_rechecks_current_teacher_before_deleting(self):
        type(self.classroom).objects.filter(pk=self.classroom.pk).update(teacher=self.other_teacher)
        with self.assertRaises(PermissionDenied):
            delete_class_assignment(actor=self.teacher, assignment=self.assignment)
        self.assert_assignment_kept()

    def test_assignment_without_learners_can_be_deleted(self):
        Enrollment.objects.filter(classroom=self.other_classroom).update(status='dropped')
        empty = assign_to_class(actor=self.admin, lesson=self.vocab, classroom=self.other_classroom,
            assigned_at=self.now, due_at=self.now + timedelta(days=1))
        self.assertEqual(empty.tasks.count(), 0)
        self.client.force_login(self.admin)
        self.assertRedirects(self.client.post(reverse('assignments:assigned_delete', args=[empty.pk])),
            reverse('assignments:assigned_list'))
        self.assertFalse(ClassAssignment.objects.filter(pk=empty.pk).exists())
        self.assert_assignment_kept()

    def test_delete_links_exist_in_assigned_list_detail_and_staff_class_page_only(self):
        self.assertContains(self.client.get(reverse('assignments:assigned_list')), self.url)
        self.assertContains(self.client.get(reverse('assignments:assigned_detail', args=[self.assignment.pk])), self.url)
        class_url = reverse('courses:class_detail', args=[self.classroom.pk])
        self.assertContains(self.client.get(class_url), self.url)
        self.client.force_login(self.student)
        response = self.client.get(class_url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.url)
        self.assertNotContains(response, 'Xóa lượt giao')

    def test_deleted_assignment_disappears_from_learner_tasks(self):
        self.client.force_login(self.student)
        skill_url = reverse('submissions:student_skill', args=['vocabulary'])
        self.assertContains(self.client.get(skill_url), self.vocab.title)
        self.client.force_login(self.teacher)
        self.client.post(self.url)
        self.client.force_login(self.student)
        self.assertNotContains(self.client.get(skill_url), self.vocab.title)
        self.assertEqual(self.client.get(reverse('submissions:do_task', args=[self.vocab_task.pk])).status_code, 404)
        self.assertTrue(LearningTask.objects.filter(pk=self.task.pk).exists())

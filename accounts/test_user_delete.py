from unittest.mock import patch
from io import StringIO

from django.contrib import admin
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.test import Client, RequestFactory
from django.urls import reverse

from ai_core.models import GradingJob
from courses.models import Enrollment
from dashboard.models import LearningTask
from dashboard.testutils import IntegratedFixture
from support.models import Conversation, Message, TutorAttempt

from .models import CustomUser, Notification
from .services import delete_user_account


class UserDeletionTests(IntegratedFixture):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin)
        self.url = reverse('accounts:user_delete', args=[self.student.pk])

    def thread(self, student=None, recipient=None, job=None):
        return Conversation.objects.create(student=student or self.student, kind='contact',
            recipient=recipient or self.teacher, recipient_role='teacher', classroom=self.classroom,
            subject='Liên hệ kiểm thử', category='other', status='waiting', job=job)

    def post_delete(self, user=None, **data):
        user = user or self.student
        return self.client.post(reverse('accounts:user_delete', args=[user.pk]),
            {'confirm_username': user.username, **data})

    def test_admin_get_previews_data_and_does_not_delete(self):
        self.thread()
        response = self.client.get(self.url)
        self.assertContains(response, 'Xóa vĩnh viễn tài khoản')
        self.assertContains(response, self.student.username)
        self.assertContains(response, 'Không thể hoàn tác')
        self.assertContains(response, 'csrfmiddlewaretoken')
        self.assertEqual(response.context['summary']['tasks'], 3)
        self.assertEqual(response.context['summary']['conversations'], 1)
        self.student.refresh_from_db()
        self.assertTrue(self.student.is_active)

    def test_delete_requires_exact_username_confirmation(self):
        for data in ({}, {'confirm_username': 'another-user'}):
            self.assertEqual(self.client.post(self.url, data).status_code, 200)
            self.assertTrue(CustomUser.objects.filter(pk=self.student.pk).exists())
        self.assertRedirects(self.post_delete(), reverse('accounts:user_list'))
        self.assertFalse(CustomUser.objects.filter(pk=self.student.pk).exists())

    def test_delete_removes_owned_submissions_and_private_conversation_without_changing_other_learners(self):
        job = GradingJob.objects.create(task=self.task, submission_key='delete-speaking', kind='speaking')
        contact = self.thread(job=job)
        private = Conversation.objects.create(student=self.student, kind='knowledge', job=job,
            subject='Trao đổi riêng với AI')
        question = Message.objects.create(conversation=private, author=self.student, role='student', body='Giải thích giúp em')
        answer = Message.objects.create(conversation=private, role='assistant', body='Giải thích')
        attempt = TutorAttempt.objects.create(conversation=private, question=question, answer=answer, status='completed')
        other = self.thread(student=self.other_student)
        sent = Message.objects.create(conversation=other, author=self.student, role='student', body='Giữ nội dung này')
        own_notification = Notification.objects.create(recipient=self.teacher, title='Có bài nộp', message='Bài kiểm thử',
            target_url=reverse('submissions:result', args=[job.pk]))
        other_id, sent_id = other.pk, sent.pk
        self.assertRedirects(self.post_delete(), reverse('accounts:user_list'))
        self.assertFalse(CustomUser.objects.filter(pk=self.student.pk).exists())
        self.assertFalse(LearningTask.objects.filter(learner_id=self.student.pk).exists())
        self.assertFalse(GradingJob.objects.filter(pk=job.pk).exists())
        self.assertFalse(Conversation.objects.filter(pk__in=[contact.pk, private.pk]).exists())
        self.assertFalse(TutorAttempt.objects.filter(pk=attempt.pk).exists())
        self.assertFalse(Notification.objects.filter(pk=own_notification.pk).exists())
        self.assertFalse(Enrollment.objects.filter(student_id=self.student.pk).exists())
        self.assertTrue(Conversation.objects.filter(pk=other_id, student=self.other_student).exists())
        sent.refresh_from_db()
        self.assertEqual(sent.pk, sent_id)
        self.assertIsNone(sent.author_id)
        self.assertEqual(sent.body, 'Giữ nội dung này')
        self.assertTrue(CustomUser.objects.filter(pk=self.other_student.pk).exists())
        self.assertEqual(self.vocab.words.count(), 2)
        self.assertTrue(type(self.classroom).objects.filter(pk=self.classroom.pk).exists())

    def test_manager_teacher_and_student_cannot_delete_accounts(self):
        for actor in (self.manager, self.teacher, self.other_student):
            self.client.force_login(actor)
            for method in ('get', 'post'):
                with self.subTest(actor=actor.role, method=method):
                    self.assertEqual(getattr(self.client, method)(self.url).status_code, 403)
                    self.assertTrue(CustomUser.objects.filter(pk=self.student.pk).exists())
            with self.assertRaises(PermissionDenied):
                delete_user_account(actor=actor, user_id=self.student.pk)

    def test_anonymous_and_inactive_actor_cannot_delete(self):
        self.client.logout()
        self.assertEqual(self.client.post(self.url, {'confirm_username': self.student.username}).status_code, 302)
        self.admin.is_active = False
        with self.assertRaises(PermissionDenied):
            delete_user_account(actor=self.admin, user_id=self.student.pk)
        self.assertTrue(CustomUser.objects.filter(pk=self.student.pk).exists())

    def test_self_and_last_admin_are_preserved(self):
        self.assertEqual(self.post_delete(self.admin).status_code, 200)
        self.assertTrue(CustomUser.objects.filter(pk=self.admin.pk, is_active=True).exists())
        with self.assertRaises(ValidationError):
            delete_user_account(actor=self.admin, user_id=self.admin.pk)

    def test_csrf_and_allowed_methods(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        client.get(self.url)
        self.assertEqual(client.post(self.url, {'confirm_username': self.student.username}).status_code, 403)
        for method in ('put', 'patch', 'delete'):
            self.assertEqual(getattr(self.client, method)(self.url).status_code, 405)
        self.assertTrue(CustomUser.objects.filter(pk=self.student.pk).exists())
        token = client.cookies['csrftoken'].value
        self.assertRedirects(client.post(self.url, {'confirm_username': self.student.username}, HTTP_X_CSRFTOKEN=token),
            reverse('accounts:user_list'))

    def test_teacher_requires_replacement_and_preserves_learners_work(self):
        job = GradingJob.objects.create(task=self.task, submission_key='teacher-final-result', kind='speaking',
            status='graded', completion_status='complete', reviewed_by=self.teacher, teacher_feedback='Đã hoàn thành')
        thread = self.thread()
        message = Message.objects.create(conversation=thread, author=self.teacher, role='staff', body='Giữ phản hồi giáo viên')
        response = self.post_delete(self.teacher)
        self.assertContains(response, 'Giáo viên tiếp nhận lớp và bài tập')
        self.teacher.refresh_from_db()
        self.assertTrue(self.teacher.is_active)
        response = self.post_delete(self.teacher, replacement_teacher=self.other_teacher.pk)
        self.assertRedirects(response, reverse('accounts:user_list'))
        self.assertFalse(CustomUser.objects.filter(pk=self.teacher.pk).exists())
        self.classroom.refresh_from_db()
        self.assertEqual(self.classroom.teacher_id, self.other_teacher.pk)
        self.task.refresh_from_db()
        self.assertEqual(self.task.teacher_id, self.other_teacher.pk)
        job.refresh_from_db()
        self.assertEqual(job.completion_status, 'complete')
        self.assertEqual(job.teacher_feedback, 'Đã hoàn thành')
        self.assertIsNone(job.reviewed_by_id)
        thread.refresh_from_db()
        self.assertEqual(thread.student_id, self.student.pk)
        self.assertEqual(thread.recipient_id, self.admin.pk)
        self.assertEqual(thread.recipient_role, 'management')
        message.refresh_from_db()
        self.assertIsNone(message.author_id)
        self.assertEqual(message.body, 'Giữ phản hồi giáo viên')

    def test_invalid_or_inactive_replacement_is_rejected(self):
        self.other_teacher.is_active = False
        self.other_teacher.save(update_fields=['is_active'])
        for replacement in (self.teacher, self.student, self.other_teacher):
            with self.subTest(replacement=replacement.username):
                with self.assertRaises(ValidationError):
                    delete_user_account(actor=self.admin, user_id=self.teacher.pk, replacement_teacher=replacement)
        self.teacher.refresh_from_db()
        self.classroom.refresh_from_db()
        self.assertEqual(self.classroom.teacher_id, self.teacher.pk)

    def test_protected_cross_user_link_rolls_back_entire_deletion(self):
        job = GradingJob.objects.create(task=self.task, submission_key='protected-job', kind='speaking')
        own = self.thread(job=job)
        other = self.thread(student=self.other_student, job=job)
        message = Message.objects.create(conversation=other, author=self.student, role='student', body='Giữ lại')
        with self.assertRaisesMessage(ValidationError, 'dữ liệu của người dùng khác'):
            delete_user_account(actor=self.admin, user_id=self.student.pk)
        self.student.refresh_from_db()
        own.refresh_from_db()
        job.refresh_from_db()
        message.refresh_from_db()
        self.assertEqual(message.author_id, self.student.pk)

    def test_deactivation_remains_a_separate_action(self):
        response = self.client.post(reverse('accounts:user_deactivate', args=[self.student.pk]))
        self.assertRedirects(response, reverse('accounts:user_list'))
        self.student.refresh_from_db()
        self.assertFalse(self.student.is_active)
        self.assertTrue(LearningTask.objects.filter(learner=self.student).exists())

    def test_owned_approved_exemption_does_not_block_account_deletion(self):
        from courses.models import ExemptionRequest
        from courses.services import ExemptionControlService

        exemption = ExemptionControlService.submit_exemption(self.student, self.classroom,
            assignment=self.assignments['vocabulary'], reason='Xin miễn bài từ vựng')
        ExemptionControlService.review(exemption.pk, self.teacher, approve=True)
        self.vocab_task.refresh_from_db()
        self.assertEqual(self.vocab_task.exemption_id, exemption.pk)
        self.assertRedirects(self.post_delete(), reverse('accounts:user_list'))
        self.assertFalse(ExemptionRequest.objects.filter(pk=exemption.pk).exists())
        self.assertFalse(CustomUser.objects.filter(pk=self.student.pk).exists())

    def test_worker_continues_when_admin_deletes_account_during_grading(self):
        GradingJob.objects.create(task=self.task, submission_key='worker-deleted-account', kind='speaking')

        def finish_after_deletion(job_id):
            delete_user_account(actor=self.admin, user_id=self.student.pk)
            return True

        output = StringIO()
        with patch('ai_core.management.commands.run_ai_worker.process_job', side_effect=finish_after_deletion):
            call_command('run_ai_worker', once=True, stdout=output)
        self.assertIn('đã được xóa', output.getvalue())

    def test_account_list_has_both_actions_for_admin_and_neither_for_manager(self):
        lock_url = reverse('accounts:user_deactivate', args=[self.student.pk])
        response = self.client.get(reverse('accounts:user_list'))
        self.assertContains(response, self.url)
        self.assertContains(response, lock_url)
        self.client.force_login(self.manager)
        response = self.client.get(reverse('accounts:user_list'))
        self.assertNotContains(response, self.url)
        self.assertNotContains(response, lock_url)

    def test_django_admin_uses_same_confirmation_and_disables_unreviewed_bulk_delete(self):
        response = self.client.get(reverse('admin:accounts_customuser_delete', args=[self.student.pk]))
        self.assertRedirects(response, self.url)
        request = RequestFactory().get('/admin/')
        request.user = self.admin
        self.assertNotIn('delete_selected', admin.site.get_model_admin(CustomUser).get_actions(request))

    def test_support_delete_permissions_allow_admin_only(self):
        request = RequestFactory().get('/admin/')
        for user in (self.admin, self.manager, self.teacher, self.student):
            request.user = user
            for model in (Conversation, Message, TutorAttempt):
                self.assertEqual(admin.site.get_model_admin(model).has_delete_permission(request), user == self.admin)

    def test_django_admin_can_delete_contact_with_messages_and_attempts(self):
        thread = self.thread()
        question = Message.objects.create(conversation=thread, author=self.student, role='student', body='Câu hỏi')
        attempt = TutorAttempt.objects.create(conversation=thread, question=question, status='failed')
        url = reverse('admin:support_conversation_delete', args=[thread.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['perms_lacking'])
        self.assertEqual(self.client.post(url, {'post': 'yes'}).status_code, 302)
        self.assertFalse(Conversation.objects.filter(pk=thread.pk).exists())
        self.assertFalse(Message.objects.filter(pk=question.pk).exists())
        self.assertFalse(TutorAttempt.objects.filter(pk=attempt.pk).exists())

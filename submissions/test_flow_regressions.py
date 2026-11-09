from datetime import timedelta
from unittest.mock import patch

from django.test import SimpleTestCase
from django.urls import reverse

from accounts.models import Notification
from assignments.models import Lesson
from assignments.services import assign_to_class
from courses.services import ClassManagementService
from dashboard.services import annotated_tasks, metrics_for
from dashboard.testutils import IntegratedFixture
from .access import is_unlocked
from .grading import grade_listening
from .models import LessonProgress
from ai_core.services import enqueue_submission


class ShortAnswerContentTests(SimpleTestCase):
    def grade(self, answer):
        return grade_listening([{'id': 1, 'correct_option': 'A', 'choice_letters': 'ABC',
            'requires_short_answer': True}], {'1': {'chosen': 'B', 'short_answer': answer}})

    def test_punctuation_symbols_and_whitespace_do_not_count_as_an_answer(self):
        for answer in ['', ' ', '.', '...', '?!', '___', '🙂', '\u200b']:
            with self.subTest(answer=answer):
                result = self.grade(answer)
                self.assertFalse(result['complete'])
                self.assertEqual(result['missing_count'], 1)
                self.assertEqual(result['details'][0]['short_answer'], answer.strip())

    def test_short_words_unicode_and_numbers_are_valid_even_when_choice_is_wrong(self):
        for answer in ['No.', 'a', '9:30', '25', 'cà phê', '東京', 'Room 3']:
            with self.subTest(answer=answer):
                result = self.grade(answer)
                self.assertTrue(result['complete'])
                self.assertEqual(result['correct_count'], 0)


class AssignmentFlowRegressionTests(IntegratedFixture):
    def save_draft(self, task, text='', answers=None):
        return self.client.post(reverse('submissions:autosave', args=[task.pk]),
            {'text': text, 'answers': answers or {}, 'reference_version': task.assignment.reference_version},
            content_type='application/json')

    def test_future_notice_opens_schedule_without_revealing_exercise_or_accepting_submission(self):
        lesson = Lesson.objects.create(skill='vocabulary', program='B1', order=80,
            title='Upcoming vocabulary', description='PRIVATE_EXERCISE_INSTRUCTIONS', created_by=self.teacher)
        lesson.words.create(word='SECRET_UPCOMING_WORD')
        assignment = assign_to_class(actor=self.teacher, lesson=lesson, classroom=self.classroom,
            assigned_at=self.now + timedelta(hours=1), due_at=self.now + timedelta(days=1), requires_previous=False)
        task = assignment.tasks.get(learner=self.student)
        notice = Notification.objects.get(recipient=self.student, event_key=f'assignment:{task.pk}')
        self.assertIn('Bài tập sắp mở', notice.title)
        self.assertIn('Mở bài:', notice.message)
        self.client.force_login(self.student)
        response = self.client.get(notice.target_url)
        self.assertContains(response, 'Bài tập sắp mở')
        for private in ['SECRET_UPCOMING_WORD', 'PRIVATE_EXERCISE_INSTRUCTIONS',
                'name="submission_key"', 'submissionForm']:
            self.assertNotContains(response, private)
        self.assertEqual(self.save_draft(task, 'too early').status_code, 400)
        self.assertEqual(self.client.post(reverse('ai_core:submit'), {'task_id': task.pk,
            'submission_key': 'too-early', 'text': 'too early'}).status_code, 404)
        with patch('submissions.views.timezone.now', return_value=assignment.assigned_at + timedelta(seconds=1)):
            self.assertContains(self.client.get(notice.target_url), 'SECRET_UPCOMING_WORD')
        self.client.force_login(self.other_student)
        self.assertEqual(self.client.get(notice.target_url).status_code, 404)

    def test_same_lesson_in_new_class_has_its_own_draft_and_dashboard_state(self):
        self.client.force_login(self.student)
        self.assertEqual(self.save_draft(self.vocab_task, 'OLD_CLASS_DRAFT').status_code, 200)
        ClassManagementService.remove_student_from_class(self.classroom, self.student)
        ClassManagementService.enroll_student_to_class(self.other_classroom, self.student)
        assignment = assign_to_class(actor=self.other_teacher, lesson=self.vocab, classroom=self.other_classroom,
            assigned_at=self.now - timedelta(minutes=1), due_at=self.now + timedelta(days=1), requires_previous=False)
        task = assignment.tasks.get(learner=self.student)
        page = self.client.get(reverse('submissions:do_task', args=[task.pk]))
        self.assertNotContains(page, 'OLD_CLASS_DRAFT')
        self.assertFalse(annotated_tasks(self.student).get(pk=task.pk).has_draft)
        self.assertEqual(metrics_for(self.student)['tasks'][0]['latest_status'], 'not_submitted')
        self.assertEqual(self.save_draft(task, 'NEW_CLASS_DRAFT').status_code, 200)
        self.vocab_task.refresh_from_db()
        self.assertEqual(self.vocab_task.draft['text'], 'OLD_CLASS_DRAFT')
        self.assertTrue(annotated_tasks(self.student).get(pk=task.pk).has_draft)
        enqueue_submission(task=task, submission_key='new-class-only', text='Customer Deadline')
        task.refresh_from_db()
        self.assertEqual(task.draft, {})
        self.assertIsNone(task.draft_saved_at)
        self.vocab_task.refresh_from_db()
        self.assertEqual(self.vocab_task.draft['text'], 'OLD_CLASS_DRAFT')

    def test_legacy_or_expired_drafts_cannot_populate_a_task(self):
        self.client.force_login(self.student)
        LessonProgress.objects.create(student=self.student, lesson=self.vocab,
            draft={'text': 'LEGACY_DRAFT'}, draft_saved_at=self.now)
        self.vocab_task.draft = {'text': 'EXPIRED_TASK_DRAFT'}
        self.vocab_task.draft_saved_at = self.now - timedelta(hours=25)
        self.vocab_task.save(update_fields=['draft', 'draft_saved_at'])
        page = self.client.get(reverse('submissions:do_task', args=[self.vocab_task.pk]))
        self.assertNotContains(page, 'LEGACY_DRAFT')
        self.assertNotContains(page, 'EXPIRED_TASK_DRAFT')
        self.assertFalse(annotated_tasks(self.student).get(pk=self.vocab_task.pk).has_draft)

    def test_symbol_only_short_answers_do_not_complete_or_unlock_the_next_lesson(self):
        lesson = Lesson.objects.create(skill='listening', program='CHUNG', order=2,
            title='Next listening', created_by=self.teacher)
        lesson.questions.create(question_text='Next question', option_a='A', option_b='B', correct_option='A')
        assignment = assign_to_class(actor=self.teacher, lesson=lesson, classroom=self.classroom,
            assigned_at=self.now - timedelta(minutes=1), due_at=self.now + timedelta(days=1))
        next_task = assignment.tasks.get(learner=self.student)
        answers = {str(q.pk): {'chosen': 'A', 'short_answer': '.'} for q in [self.q1, self.q2]}
        job, _ = enqueue_submission(task=self.listening_task, submission_key='punctuation-only', answers=answers)
        self.assertEqual(job.completion_status, 'incomplete')
        self.assertFalse(is_unlocked(next_task))
        self.assertEqual(metrics_for(self.student)['completed_count'], 0)
        for row in answers.values():
            row['short_answer'] = '9:30'
        job, _ = enqueue_submission(task=self.listening_task, submission_key='actual-heard-number', answers=answers)
        self.assertEqual(job.completion_status, 'complete')
        self.assertTrue(is_unlocked(next_task))

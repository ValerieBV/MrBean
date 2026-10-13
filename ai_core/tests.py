import json
import tempfile
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from dashboard.models import LearningTask
from .models import GradingJob
from .providers import OpenAIGrader, validate_result
from .services import enqueue_submission, expire_jobs, process_job


GOOD = {'vocabulary': 8, 'grammar': 6, 'pronunciation': None, 'feedback': 'Sửa thì quá khứ.', 'needs_manual': False}


class GradingTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.student = User.objects.create_user(username='student', role='student')
        self.teacher = User.objects.create_user(username='teacher', role='teacher')
        self.other = User.objects.create_user(username='other', role='teacher')
        self.task = LearningTask.objects.create(assignment_key='a1', title='Vocabulary', learner=self.student,
                                               teacher=self.teacher, due_at=timezone.now() + timedelta(days=1))

    def job(self, key='s1', **kwargs):
        return enqueue_submission(task=self.task, submission_key=key, kind='vocabulary', text='I went home.', **kwargs)[0]

    def test_success_idempotency_and_single_claim(self):
        job = self.job()
        duplicate = self.job()
        self.assertEqual(job.pk, duplicate.pk)
        provider = Mock()
        provider.grade.return_value = GOOD
        self.assertTrue(process_job(job.pk, provider))
        self.assertFalse(process_job(job.pk, provider))
        provider.grade.assert_called_once()
        job.refresh_from_db()
        self.assertEqual(job.status, 'ai_reviewed')
        self.assertEqual(job.suggested_score, 7)
        self.assertIsNone(job.final_score)
        self.assertLessEqual(provider.grade.call_args.kwargs['timeout'], 120)

    def test_ai_failure_and_timeout_fallback(self):
        for index, error in enumerate([RuntimeError('secret'), TimeoutError()]):
            job = self.job(str(index))
            provider = Mock()
            provider.grade.side_effect = error
            process_job(job.pk, provider)
            job.refresh_from_db()
            self.assertEqual(job.status, 'manual')
            self.assertNotIn('secret', job.fallback_reason)

    def test_deadline_queued_and_interrupted_processing(self):
        now = timezone.now()
        jobs = [self.job('queued'), self.job('processing')]
        for job, status in zip(jobs, ['queued', 'processing']):
            GradingJob.objects.filter(pk=job.pk).update(status=status, submitted_at=now - timedelta(seconds=300))
        self.assertEqual(expire_jobs(now), 2)
        provider = Mock()
        self.assertFalse(process_job(jobs[0].pk, provider))
        provider.grade.assert_not_called()
        self.assertEqual(GradingJob.objects.filter(status='manual').count(), 2)

    def test_late_result_not_saved(self):
        job = self.job()
        provider = Mock()
        def late(*args, **kwargs):
            GradingJob.objects.filter(pk=job.pk).update(status='manual', fallback_reason='ai_deadline_exceeded')
            return GOOD
        provider.grade.side_effect = late
        process_job(job.pk, provider)
        job.refresh_from_db()
        self.assertEqual(job.status, 'manual')
        self.assertEqual(job.result, {})

    def test_result_at_five_minute_boundary(self):
        job = self.job()
        start = job.submitted_at
        provider = Mock()
        provider.grade.return_value = GOOD
        with patch('ai_core.services.timezone.now', side_effect=[start, start, start + timedelta(seconds=300), start + timedelta(seconds=300)]):
            process_job(job.pk, provider)
        job.refresh_from_db()
        self.assertEqual(job.status, 'manual')

    def test_invalid_ai_results(self):
        for result in [dict(GOOD, grammar=11), dict(GOOD, grammar=True), dict(GOOD, grammar=float('nan')),
                       dict(GOOD, needs_manual=True), dict(GOOD, feedback=''), dict(GOOD, pronunciation=9), []]:
            with self.assertRaises(ValueError):
                validate_result(result, 'vocabulary')
        with self.assertRaises(ValueError):
            validate_result(GOOD, 'speaking')

    def test_missing_speaking_audio_goes_manual(self):
        job, _ = enqueue_submission(task=self.task, submission_key='audio', kind='speaking')
        process_job(job.pk)
        job.refresh_from_db()
        self.assertEqual(job.status, 'manual')

    def test_invalid_submission(self):
        for key, kind, text in [('', 'vocabulary', 'word'), ('valid', 'other', 'word'), ('valid', 'vocabulary', '')]:
            with self.assertRaises(ValidationError):
                enqueue_submission(task=self.task, submission_key=key, kind=kind, text=text)

    def test_cross_task_duplicate_rejected(self):
        self.job()
        second = LearningTask.objects.create(assignment_key='a2', title='Next', learner=self.student,
                                             teacher=self.teacher, due_at=timezone.now())
        with self.assertRaises(ValidationError):
            enqueue_submission(task=second, submission_key='s1', kind='vocabulary', text='test')

    def test_review_access_validation_and_double_review(self):
        job = self.job()
        GradingJob.objects.filter(pk=job.pk).update(status='manual')
        url = f'/ai/jobs/{job.pk}/review/'
        body = {'score': 8, 'feedback': 'Tốt, cần luyện thêm.'}
        self.assertEqual(self.client.post(url, body, content_type='application/json').status_code, 401)
        self.client.force_login(self.student)
        self.assertEqual(self.client.post(url, body, content_type='application/json').status_code, 403)
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(url, body, content_type='application/json').status_code, 404)
        self.client.force_login(self.teacher)
        for invalid in [dict(body, score=11), dict(body, score=True), dict(body, feedback=''), []]:
            self.assertEqual(self.client.post(url, invalid, content_type='application/json').status_code, 400)
        self.assertEqual(self.client.post(url, body, content_type='application/json').status_code, 200)
        self.assertEqual(self.client.post(url, body, content_type='application/json').status_code, 409)
        job.refresh_from_db()
        self.assertEqual(job.reviewed_by, self.teacher)
        self.assertEqual(job.final_score, 8)

    def test_submission_and_detail_scope(self):
        self.client.force_login(self.student)
        body = {'task_id': self.task.pk, 'submission_key': 'api', 'kind': 'vocabulary', 'text': 'test'}
        response = self.client.post('/ai/submissions/', body, content_type='application/json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.client.post('/ai/submissions/', body, content_type='application/json').status_code, 200)
        self.assertEqual(self.client.post('/ai/submissions/', [], content_type='application/json').status_code, 400)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(f'/ai/jobs/{response.json()["id"]}/').status_code, 404)
        self.assertEqual(self.client.post('/ai/submissions/', body, content_type='application/json').status_code, 404)

    @override_settings(OPENAI_API_KEY='test-only-key')
    def test_audio_adapter_sends_actual_audio_and_validates_json(self):
        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            job, _ = enqueue_submission(task=self.task, submission_key='speech', kind='speaking',
                                        audio=SimpleUploadedFile('speech.wav', b'RIFF-test-audio', content_type='audio/wav'))
            result = dict(GOOD, pronunciation=7)
            with patch('openai.OpenAI') as client:
                api = client.return_value.__enter__.return_value
                api.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(
                    message=SimpleNamespace(content=json.dumps(result)))])
                self.assertEqual(OpenAIGrader().grade(job, 30), result)
                params = api.chat.completions.create.call_args.kwargs
                self.assertEqual(params['modalities'], ['text'])
                self.assertEqual(params['messages'][1]['content'][1]['type'], 'input_audio')
                self.assertFalse(params['store'])
                client.assert_called_once_with(api_key='test-only-key', timeout=30, max_retries=0)

    def test_worker_once(self):
        job = self.job()
        with patch('ai_core.services.OpenAIGrader') as provider:
            provider.return_value.grade.return_value = GOOD
            call_command('run_ai_worker', once=True)
        job.refresh_from_db()
        self.assertEqual(job.status, 'ai_reviewed')

    def test_csrf_required_for_browser_review(self):
        from django.test import Client
        job = self.job()
        GradingJob.objects.filter(pk=job.pk).update(status='manual')
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.teacher)
        browser.get('/dashboard/')
        url = f'/ai/jobs/{job.pk}/review/'
        body = {'score': 8, 'feedback': 'Đã chấm.'}
        self.assertEqual(browser.post(url, body, content_type='application/json').status_code, 403)
        self.assertEqual(browser.post(url, body, content_type='application/json',
                                      HTTP_X_CSRFTOKEN=browser.cookies['csrftoken'].value).status_code, 200)

    def test_audio_access_and_missing_file(self):
        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            job, _ = enqueue_submission(task=self.task, submission_key='private', kind='speaking',
                                        audio=SimpleUploadedFile('private.wav', b'RIFF-private'))
            url = f'/ai/jobs/{job.pk}/audio/'
            self.assertEqual(self.client.get(url).status_code, 401)
            self.client.force_login(self.other)
            self.assertEqual(self.client.get(url).status_code, 404)
            self.client.force_login(self.teacher)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(b''.join(response.streaming_content), b'RIFF-private')
            response.close()

    def test_queued_job_cannot_be_reviewed(self):
        job = self.job()
        self.client.force_login(self.teacher)
        response = self.client.post(f'/ai/jobs/{job.pk}/review/',
                                    {'score': 7, 'feedback': 'test'}, content_type='application/json')
        self.assertEqual(response.status_code, 409)

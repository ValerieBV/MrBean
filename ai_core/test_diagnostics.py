import io
import json
from datetime import timedelta
from unittest.mock import Mock, patch
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from dashboard.testutils import IntegratedFixture
from .diagnostics import failure_reason
from .models import GradingJob
from .services import enqueue_submission, process_job


class GradingDiagnosticTests(IntegratedFixture):
    def job(self, key='diagnostic', **extra):
        return GradingJob.objects.create(task=self.vocab_task, submission_key=key, kind='vocabulary',
            rubric_snapshot=self.vocab_task.assignment.rubric, **extra)

    def test_pending_jobs_do_not_enter_teacher_review_queue(self):
        for status in ('queued', 'processing'):
            self.job(status, status=status)
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(reverse('dashboard:metrics')).json()['review_queue'], [])

    def test_success_and_manual_queue_labels_are_distinct_without_scores(self):
        self.job('success', status='ai_reviewed', suggested_score=9.99)
        self.job('manual', status='manual', fallback_reason='ai_authentication')
        self.client.force_login(self.teacher)
        rows = self.client.get(reverse('dashboard:metrics')).json()['review_queue']
        self.assertEqual({row['review_status_label'] for row in rows}, {'Chờ giáo viên xác nhận', 'Cần chấm thủ công'})
        for row in rows:
            self.assertNotIn('final_score',row); self.assertNotIn('suggested_score', row)

    def test_safe_manual_hint_visible_only_to_staff_with_access(self):
        job = self.job(status='manual', fallback_reason='provider_not_configured')
        url = reverse('submissions:result', args=[job.pk])
        for user in [self.teacher, self.admin, self.manager]:
            self.client.force_login(user)
            self.assertContains(self.client.get(url), 'data-grading-reason="provider_not_configured"')
        self.client.force_login(self.other_teacher)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.student)
        response = self.client.get(url)
        self.assertNotContains(response, 'data-grading-reason=')
        self.assertNotContains(response, 'Tiến trình chấm chưa nhận được API key')
        self.assertNotIn('fallback_reason', self.client.get(reverse('ai_core:detail', args=[job.pk])).json())

    @override_settings(OPENAI_API_KEY='')
    def test_worker_missing_key_is_reported_without_masking_as_generic_error(self):
        job, _ = enqueue_submission(task=self.vocab_task, submission_key='missing-key', text='Customer')
        output = io.StringIO()
        call_command('run_ai_worker', once=True, stdout=output)
        job.refresh_from_db()
        self.assertEqual(job.fallback_reason, 'provider_not_configured')
        self.assertIn('Tiến trình chưa nhận OPENAI_API_KEY', output.getvalue())
        self.assertIn('nguyên nhân=provider_not_configured', output.getvalue())

    def test_uncertain_evidence_is_not_reported_as_api_failure(self):
        job, _ = enqueue_submission(task=self.vocab_task, submission_key='uncertain', text='Customer')
        provider = Mock(); provider.grade.return_value = {'needs_manual': True, 'feedback': 'Không đọc rõ', 'counts': []}
        process_job(job.pk, provider); job.refresh_from_db()
        self.assertEqual(job.fallback_reason, 'ai_uncertain_evidence')

    def test_worker_explains_expired_old_jobs_without_sending_them_to_openai(self):
        job = self.job(submitted_at=self.now-timedelta(minutes=8))
        output = io.StringIO()
        with patch('ai_core.services.OpenAIGrader') as api:
            call_command('run_ai_worker', once=True, stdout=output)
            api.assert_not_called()
        job.refresh_from_db()
        self.assertEqual(job.fallback_reason, 'ai_deadline_exceeded')
        self.assertIn('1 bài đã quá 5 phút', output.getvalue())

    def test_known_validation_failures_have_safe_codes(self):
        cases = [(ValueError('missing_rubric'), 'ai_invalid_reference'),
                 (ValueError('invalid_count'), 'ai_invalid_result'),
                 (ValueError('invalid_transcript'), 'ai_invalid_evidence'),
                 (FileNotFoundError('private-file-name'), 'ai_evidence_missing'),
                 (json.JSONDecodeError('private-submission', '', 0), 'ai_invalid_result'),
                 (ValueError('secret-unrecognized-error'), 'ai_error')]
        for error, expected in cases:
            with self.subTest(expected=expected):self.assertEqual(failure_reason(error), expected)

    @override_settings(OPENAI_API_KEY='secret-do-not-display')
    def test_queue_diagnostic_is_read_only_offline_and_never_prints_private_values(self):
        old = self.job('old-queued', submitted_at=self.now-timedelta(minutes=8), text='PRIVATE_SUBMISSION')
        manual = self.job('manual', status='manual', fallback_reason='ai_quota_exceeded')
        self.job('unknown', status='manual', fallback_reason='secret-unrecognized-error')
        output = io.StringIO()
        with patch('openai.OpenAI') as api:
            call_command('check_ai_queue', stdout=output)
            api.assert_not_called()
        old.refresh_from_db(); self.assertEqual(old.status, 'queued')
        for private in ('secret-do-not-display', 'PRIVATE_SUBMISSION', 'secret-unrecognized-error'):
            self.assertNotIn(private, output.getvalue())
        self.assertIn('queued: 1', output.getvalue())
        output = io.StringIO(); call_command('check_ai_queue', job=manual.pk, stdout=output)
        self.assertIn('ai_quota_exceeded', output.getvalue())

    def test_queue_diagnostic_explains_success_and_rejects_unknown_job(self):
        from django.core.management.base import CommandError
        job = self.job(status='ai_reviewed')
        output = io.StringIO(); call_command('check_ai_queue', job=job.pk, stdout=output)
        self.assertIn('AI đã đánh giá thành công', output.getvalue())
        with self.assertRaises(CommandError):call_command('check_ai_queue', job=job.pk+100, stdout=io.StringIO())

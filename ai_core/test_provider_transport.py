"""Exercise the installed OpenAI SDK and durable worker without paid API calls."""
import io
import json
from unittest.mock import patch
import httpx
from openai import OpenAI
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from dashboard.testutils import IntegratedFixture
from .services import enqueue_submission, process_job


@override_settings(OPENAI_API_KEY='transport-test-secret')
class ProviderTransportTests(IntegratedFixture):
    def client_for(self, handler):
        return OpenAI(api_key='transport-test-secret', max_retries=0,
                      http_client=httpx.Client(transport=httpx.MockTransport(handler)))

    @staticmethod
    def response(payload):
        return httpx.Response(200, json={'id': 'resp_test', 'object': 'response', 'created_at': 0,
            'model': 'gpt-6-luna', 'status': 'completed', 'output': [{'id': 'msg_test',
            'type': 'message', 'role': 'assistant', 'status': 'completed', 'content': [
                {'type': 'output_text', 'text': json.dumps(payload), 'annotations': []}]}]})

    def test_image_sdk_worker_and_teacher_confirmation_are_separate_states(self):
        stream = io.BytesIO(); Image.new('RGB', (20, 20), 'white').save(stream, 'PNG')
        job, _ = enqueue_submission(task=self.vocab_task, submission_key='transport-image', text='typed duplicate',
            images=[SimpleUploadedFile('page.png', stream.getvalue())])
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(reverse('dashboard:metrics')).json()['review_queue'], [])
        requests = []

        def handler(request):
            self.assertEqual(request.url.path, '/v1/responses')
            requests.append(json.loads(request.content))
            return self.response({'needs_manual': False, 'feedback': 'Đã viết đủ lượt.', 'counts': [
                {'word': 'Customer', 'count': 3}, {'word': 'Deadline', 'count': 3}]})

        output = io.StringIO()
        with patch('openai.OpenAI', return_value=self.client_for(handler)):
            call_command('run_ai_worker', once=True, stdout=output)
        job.refresh_from_db()
        self.assertEqual(job.status, 'ai_reviewed'); self.assertEqual(job.suggested_score, 10)
        self.assertIsNone(job.final_score)
        self.assertIn('AI đã đánh giá, chờ giáo viên xác nhận', output.getvalue())
        self.assertNotIn('transport-test-secret', output.getvalue())
        self.assertEqual(len(requests), 1)
        self.assertFalse(requests[0]['store'])
        content = requests[0]['input'][0]['content']
        self.assertEqual(json.loads(content[0]['text'])['submission'], '')
        self.assertEqual(content[1]['type'], 'input_image')
        self.assertTrue(content[1]['image_url'].startswith('data:image/jpeg;base64,'))
        self.assertTrue(requests[0]['text']['format']['strict'])
        queue = self.client.get(reverse('dashboard:metrics')).json()['review_queue']
        self.assertEqual(queue[0]['review_status_label'], 'Chờ giáo viên xác nhận')
        self.assertNotIn('suggested_score', queue[0])
        response = self.client.get(reverse('submissions:result', args=[job.pk]))
        self.assertContains(response, 'data-grading-state="ai_reviewed"')
        self.assertContains(response, 'AI đã đánh giá — chờ giáo viên xác nhận')
        self.assertContains(response, 'id="reviewForm"')
        self.client.force_login(self.student)
        response = self.client.get(reverse('submissions:result', args=[job.pk]))
        self.assertNotContains(response, 'data-grading-state=')
        self.assertNotContains(response, 'Đã viết đủ lượt.')
        self.assertNotContains(response, 'id="resultPoll"')
        self.assertIsNone(self.client.get(reverse('ai_core:detail', args=[job.pk])).json()['final_score'])

    def test_recording_sdk_transcription_then_structured_grade(self):
        job, _ = enqueue_submission(task=self.task, submission_key='transport-audio', audio=self.audio())
        paths = []

        def handler(request):
            paths.append(request.url.path)
            if request.url.path == '/v1/audio/transcriptions':
                self.assertIn('multipart/form-data', request.headers['content-type'])
                self.assertNotIn(b'My hobby is reading.', request.content)
                return httpx.Response(200, json={'text': 'My hobby is swimming.'})
            evidence = json.loads(json.loads(request.content)['input'][0]['content'][0]['text'])
            self.assertEqual(evidence['comparison']['different_words'], 1)
            return self.response({'needs_manual': False, 'feedback': 'Transcript khác một từ; cần nghe lại bản ghi.'})

        with patch('openai.OpenAI', return_value=self.client_for(handler)):
            process_job(job.pk)
        job.refresh_from_db()
        self.assertEqual(paths, ['/v1/audio/transcriptions', '/v1/responses'])
        self.assertEqual(job.status, 'ai_reviewed'); self.assertEqual(job.suggested_score, 7.5)
        self.assertEqual(job.transcript, 'My hobby is swimming.')

    def test_sdk_http_failures_keep_safe_specific_reasons(self):
        cases = [(401, 'invalid_api_key', 'ai_authentication'),
                 (403, 'permission_denied', 'ai_permission_denied'),
                 (404, 'model_not_found', 'ai_model_unavailable'),
                 (429, 'insufficient_quota', 'ai_quota_exceeded'),
                 (429, 'rate_limit_exceeded', 'ai_rate_limited'),
                 (400, 'invalid_request_error', 'ai_request_invalid'),
                 (503, 'server_error', 'ai_provider_unavailable')]
        for index, (status, code, expected) in enumerate(cases):
            with self.subTest(status=status, code=code):
                job, _ = enqueue_submission(task=self.vocab_task, submission_key=f'transport-error-{index}', text='Customer')

                def handler(request):
                    return httpx.Response(status, json={'error': {'message': 'transport-test-secret PRIVATE_SUBMISSION',
                        'type': 'invalid_request_error', 'code': code}})

                with patch('openai.OpenAI', return_value=self.client_for(handler)), self.assertLogs('ai_core.services') as logs:
                    process_job(job.pk)
                job.refresh_from_db()
                self.assertEqual((job.status, job.fallback_reason), ('manual', expected))
                self.assertIn(expected, '\n'.join(logs.output))
                self.assertNotIn('transport-test-secret', '\n'.join(logs.output))
                self.assertNotIn('PRIVATE_SUBMISSION', '\n'.join(logs.output))

    def test_sdk_connection_and_timeout_have_distinct_reasons(self):
        for index, (exception, expected) in enumerate([(httpx.ConnectError, 'ai_connection_error'),
                                                      (httpx.ReadTimeout, 'ai_timeout')]):
            with self.subTest(reason=expected):
                job, _ = enqueue_submission(task=self.vocab_task, submission_key=f'transport-network-{index}', text='Customer')

                def handler(request):
                    raise exception('transport-test-secret', request=request)

                with patch('openai.OpenAI', return_value=self.client_for(handler)):
                    process_job(job.pk)
                job.refresh_from_db()
                self.assertEqual(job.fallback_reason, expected)

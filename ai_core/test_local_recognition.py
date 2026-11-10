"""Local checkpoint integration and privacy checks, with no paid API calls."""
import io
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from PIL import Image

from dashboard.testutils import IntegratedFixture
from .local_recognition import collect_local_evidence, inspect_model, model_directory, public_recognition_report
from .services import enqueue_submission, process_job


def model_files(folder, kind='vocabulary'):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    config = {'model_type': 'vision-encoder-decoder', 'decoder': {'model_type': 'trocr'}} if kind == 'vocabulary' else {'model_type': 'whisper'}
    (folder / 'config.json').write_text(json.dumps(config))
    (folder / 'preprocessor_config.json').write_text('{}')
    (folder / 'tokenizer_config.json').write_text('{}')
    (folder / 'tokenizer.json').write_text('{}')
    (folder / 'model.safetensors').write_bytes(b'fake-weights-for-inspection-only')
    return folder


@override_settings(AI_LOCAL_ENABLED=True)
class CheckpointInspectionTests(SimpleTestCase):
    def test_relative_path_uses_project_root_not_terminal_working_directory(self):
        with override_settings(BASE_DIR=Path('/project'), AI_LOCAL_VOCAB_MODEL_DIR='ai_models/vocabulary/best_model'):
            self.assertEqual(model_directory('vocabulary'), Path('/project/ai_models/vocabulary/best_model'))

    def test_missing_disabled_and_incomplete_are_reported_without_importing_torch(self):
        with tempfile.TemporaryDirectory() as folder, override_settings(AI_LOCAL_VOCAB_MODEL_DIR=folder, AI_LOCAL_ENABLED=True):
            self.assertEqual(inspect_model('vocabulary')['status'], 'incomplete')
            with override_settings(AI_LOCAL_ENABLED=False):
                self.assertEqual(inspect_model('vocabulary')['status'], 'disabled')
            with override_settings(AI_LOCAL_VOCAB_MODEL_DIR=str(Path(folder) / 'missing')):
                self.assertEqual(inspect_model('vocabulary')['status'], 'missing')

    def test_lfs_pointer_is_not_treated_as_trained_weights(self):
        with tempfile.TemporaryDirectory() as folder, override_settings(AI_LOCAL_VOCAB_MODEL_DIR=folder):
            model_files(folder)
            (Path(folder) / 'model.safetensors').write_text('version https://git-lfs.github.com/spec/v1\noid sha256:123\nsize 250000000\n')
            self.assertEqual(inspect_model('vocabulary')['status'], 'lfs_pointer')

    def test_kind_processor_and_sharded_weights_are_checked(self):
        with tempfile.TemporaryDirectory() as folder, override_settings(AI_LOCAL_VOCAB_MODEL_DIR=folder, AI_LOCAL_SPEAKING_MODEL_DIR=folder):
            path = model_files(folder)
            self.assertEqual(inspect_model('vocabulary')['status'], 'ready')
            self.assertEqual(inspect_model('speaking')['status'], 'wrong_kind')
            (path / 'model.safetensors').rename(path / 'model-00001-of-00002.safetensors')
            (path / 'model.safetensors.index.json').write_text(json.dumps({'weight_map': {'a': 'model-00001-of-00002.safetensors', 'b': 'model-00002-of-00002.safetensors'}}))
            self.assertEqual(inspect_model('vocabulary')['status'], 'incomplete')
            (path / 'model-00002-of-00002.safetensors').write_bytes(b'other-weights-for-inspection-only')
            self.assertEqual(inspect_model('vocabulary')['status'], 'ready')
            (path / 'preprocessor_config.json').unlink()
            self.assertEqual(inspect_model('vocabulary')['status'], 'incomplete')

    def test_shard_path_cannot_escape_model_folder(self):
        with tempfile.TemporaryDirectory() as folder, override_settings(AI_LOCAL_VOCAB_MODEL_DIR=folder):
            path = model_files(folder)
            (path / 'model.safetensors.index.json').write_text(json.dumps({'weight_map': {'a': '../other.safetensors'}}))
            self.assertEqual(inspect_model('vocabulary')['status'], 'incomplete')

    def test_replacing_processor_changes_cache_identity(self):
        with tempfile.TemporaryDirectory() as folder, override_settings(AI_LOCAL_VOCAB_MODEL_DIR=folder):
            path = model_files(folder)
            before = inspect_model('vocabulary')['cache_key']
            (path / 'tokenizer_config.json').write_text('{"changed": true}')
            self.assertNotEqual(inspect_model('vocabulary')['cache_key'], before)

    def test_read_only_command_and_strict_failures_never_call_api(self):
        with tempfile.TemporaryDirectory() as folder, override_settings(AI_LOCAL_VOCAB_MODEL_DIR=folder), patch('openai.OpenAI') as api:
            output = io.StringIO()
            call_command('check_local_models', kind='vocabulary', stdout=output)
            self.assertIn('incomplete', output.getvalue())
            with self.assertRaises(CommandError):
                call_command('check_local_models', kind='vocabulary', strict=True, stdout=io.StringIO())
            api.assert_not_called()

    def test_api_report_does_not_expose_paths_or_private_error_messages(self):
        report = public_recognition_report({'kind': 'vocabulary', 'status': 'error', 'used': False,
            'path': 'SECRET_PATH', 'hint': 'SECRET_API_KEY', 'error': 'SECRET_SUBMISSION'})
        self.assertNotIn('SECRET', json.dumps(report))


@override_settings(OPENAI_API_KEY='test-local-key', AI_LOCAL_ENABLED=True)
class LocalRecognitionWorkflowTests(IntegratedFixture):
    def api(self, counts=None, error=None):
        factory = patch('openai.OpenAI')
        client = factory.start()
        self.addCleanup(factory.stop)
        api = client.return_value.__enter__.return_value
        api.with_options.return_value = api
        api.audio.transcriptions.create.return_value = SimpleNamespace(text='My hobby is reading.')
        api.responses.create.return_value = SimpleNamespace(output_text=json.dumps({
            'needs_manual': False, 'feedback': 'Đã đối chiếu ảnh gốc.', 'counts': counts or [
                {'word': 'Customer', 'count': 3}, {'word': 'Deadline', 'count': 3}]}))
        if error:
            api.responses.create.side_effect = error
        return api

    def vocab_job(self, key='local'):
        return enqueue_submission(task=self.vocab_task, submission_key=key, images=[self.vocabulary_image()])[0]

    def evidence(self, text='Customer', status='used'):
        return {'kind': 'vocabulary', 'status': status, 'used': bool(text), 'advisory_only': True,
            'recognizer': 'local_trocr', 'text': text, 'exhaustive': False}

    def test_local_missing_words_do_not_override_verified_image_counts(self):
        job = self.vocab_job()
        api = self.api()
        with patch('ai_core.local_recognition.collect_local_evidence', return_value=self.evidence()):
            process_job(job.pk)
        job.refresh_from_db()
        self.assertEqual(job.status, 'ai_reviewed')
        self.assertTrue(job.result['complete'])
        self.assertEqual(job.result['details'][1]['observed'], 3)
        self.assertEqual(job.grading_method, 'local_openai')
        self.assertEqual(job.completion_status, 'pending')
        content = api.responses.create.call_args.kwargs['input'][0]['content']
        evidence = json.loads(content[0]['text'])
        self.assertEqual(evidence['submission'], '')
        self.assertTrue(evidence['recognition_supplement']['advisory_only'])
        self.assertEqual(content[1]['type'], 'input_image')
        self.assertIn('ảnh gốc', api.responses.create.call_args.kwargs['instructions'])

    def test_definitions_and_ocr_repetitions_are_not_counted_on_the_server(self):
        job = self.vocab_job('definitions')
        self.api(counts=[{'word': 'Customer', 'count': 1}, {'word': 'Deadline', 'count': 0}])
        with patch('ai_core.local_recognition.collect_local_evidence', return_value=self.evidence('Customer ' * 50 + 'Deadline ' * 50)):
            process_job(job.pk)
        job.refresh_from_db()
        self.assertFalse(job.result['complete'])
        self.assertEqual(job.result['matched_total'], 1)

    def test_empty_and_broken_local_model_keep_original_openai_route(self):
        for index, status in enumerate(['empty', 'missing', 'dependencies', 'error', 'timeout']):
            with self.subTest(status=status):
                job = self.vocab_job('fallback-' + str(index))
                api = self.api()
                with patch('ai_core.local_recognition.collect_local_evidence', return_value=self.evidence('', status)):
                    process_job(job.pk)
                job.refresh_from_db()
                self.assertEqual(job.status, 'ai_reviewed')
                self.assertTrue(job.result['complete'])
                self.assertEqual(job.grading_method, 'openai')
                evidence = json.loads(api.responses.create.call_args.kwargs['input'][0]['content'][0]['text'])
                self.assertNotIn('recognition_supplement', evidence)

    def test_api_failure_preserves_local_reading_but_never_publishes_a_grade(self):
        job = self.vocab_job('api-failure')
        self.api(error=TimeoutError('SECRET_KEY'))
        with patch('ai_core.local_recognition.collect_local_evidence', return_value=self.evidence('Customer Deadline')):
            process_job(job.pk)
        job.refresh_from_db()
        self.assertEqual((job.status, job.fallback_reason), ('manual', 'ai_timeout'))
        self.assertEqual(job.result['recognition']['text'], 'Customer Deadline')
        self.assertNotIn('complete', job.result)
        self.assertEqual(job.completion_status, 'pending')
        self.client.force_login(self.teacher)
        self.assertContains(self.client.get(reverse('submissions:result', args=[job.pk])), 'data-local-recognition')

    def test_omitted_word_count_requires_review_instead_of_becoming_zero(self):
        job = self.vocab_job('missing-count')
        self.api(counts=[{'word': 'Customer', 'count': 3}])
        with patch('ai_core.local_recognition.collect_local_evidence', return_value=self.evidence('Customer Deadline')):
            process_job(job.pk)
        job.refresh_from_db()
        self.assertEqual((job.status, job.fallback_reason), ('manual', 'ai_invalid_result'))
        self.assertNotIn('details', job.result)
        self.assertNotIn('complete', job.result)
        self.assertEqual(job.completion_status, 'pending')

    def test_local_model_evidence_is_staff_only_and_html_is_escaped(self):
        job = self.vocab_job('private')
        self.api()
        private_text = '<script>alert("LOCAL_PRIVATE_TEXT")</script>'
        with patch('ai_core.local_recognition.collect_local_evidence', return_value=self.evidence(private_text)):
            process_job(job.pk)
        for user in (self.teacher, self.admin, self.manager):
            self.client.force_login(user)
            response = self.client.get(reverse('submissions:result', args=[job.pk]))
            self.assertContains(response, 'LOCAL_PRIVATE_TEXT')
            self.assertNotContains(response, private_text)
        self.client.force_login(self.teacher)
        detail = self.client.get(reverse('ai_core:detail', args=[job.pk])).json()
        self.assertEqual(detail['result']['recognition']['text'], private_text)
        self.client.force_login(self.student)
        self.assertNotContains(self.client.get(reverse('submissions:result', args=[job.pk])), 'LOCAL_PRIVATE_TEXT')
        self.assertNotIn('LOCAL_PRIVATE_TEXT', self.client.get(reverse('ai_core:detail', args=[job.pk])).content.decode())
        self.client.force_login(self.other_teacher)
        self.assertEqual(self.client.get(reverse('submissions:result', args=[job.pk])).status_code, 404)

    def test_speaking_keeps_primary_openai_transcript_and_adds_whisper_evidence(self):
        job, _ = enqueue_submission(task=self.task, submission_key='whisper-assist', audio=self.audio())
        api = self.api()
        api.responses.create.return_value = SimpleNamespace(output_text=json.dumps({
            'needs_manual': False, 'feedback': 'Cần nghe lại bản ghi.', 'complete': None}))
        local = {**self.evidence('My hobby is swimming.'), 'kind': 'speaking', 'recognizer': 'local_whisper'}
        with patch('ai_core.local_recognition.collect_local_evidence', return_value=local):
            process_job(job.pk)
        job.refresh_from_db()
        self.assertEqual(job.transcript, 'My hobby is reading.')
        self.assertEqual(job.result['transcript_source'], 'openai_transcription')
        self.assertIsNone(job.result['complete'])
        api.audio.transcriptions.create.assert_called_once()
        self.assertNotIn('prompt', api.audio.transcriptions.create.call_args.kwargs)

    def test_remote_model_cannot_forge_local_provenance(self):
        job = self.vocab_job('forged')
        api = self.api()
        payload = json.loads(api.responses.create.return_value.output_text)
        payload['recognition'] = self.evidence('FORGED_CHECKPOINT')
        api.responses.create.return_value.output_text = json.dumps(payload)
        with patch('ai_core.local_recognition.collect_local_evidence', return_value=self.evidence('', 'missing')):
            process_job(job.pk)
        job.refresh_from_db()
        self.assertEqual(job.result['recognition']['status'], 'missing')
        self.assertNotIn('FORGED_CHECKPOINT', json.dumps(job.result))

    def test_collector_uses_page_order_limits_text_and_does_not_count_words(self):
        job = self.vocab_job('collector')
        ready = {'status': 'ready', 'path': '/unused'}
        with patch('ai_core.local_recognition.inspect_model', return_value=ready), patch(
                'ai_core.local_recognition.recognize_image', return_value=([{'text': 'Customer', 'box': [0, 0, 20, 20]}], False)):
            report = collect_local_evidence(job, 5)
        self.assertEqual(report['lines'][0]['page'], 1)
        self.assertEqual(report['text'], 'Customer')
        self.assertFalse(report['exhaustive'])
        self.assertNotIn('counts', report)

    def test_collector_catches_model_errors_without_leaking_messages(self):
        job = self.vocab_job('collector-error')
        with patch('ai_core.local_recognition.inspect_model', return_value={'status': 'ready'}), patch(
                'ai_core.local_recognition.recognize_image', side_effect=RuntimeError('SECRET_PATH_AND_CONTENT')):
            report = collect_local_evidence(job, 5)
        self.assertEqual(report['status'], 'error')
        self.assertNotIn('SECRET', json.dumps(report))

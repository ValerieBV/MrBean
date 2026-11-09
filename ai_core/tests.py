import io
import json
import tempfile
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch
from PIL import Image
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client, override_settings
from django.utils import timezone
from dashboard.testutils import IntegratedFixture
from .models import GradingJob
from .services import enqueue_submission, process_job, expire_jobs
from .providers import validate_result, OpenAIGrader

GOOD = {'complete':True,'transcript':'My hobby is reading.','feedback':'Transcript khớp lời mẫu. Giáo viên kiểm tra bản ghi.','needs_manual':False}


class GradingTests(IntegratedFixture):
    def job(self,key='s1'):
        return enqueue_submission(task=self.task,submission_key=key,audio=self.audio())[0]

    def post(self,user,task=None,**extra):
        self.client.force_login(user)
        data={'task_id':(task or self.task).pk,'submission_key':'api1','audio':self.audio(),**extra}
        return self.client.post('/ai/submissions/', data)

    def test_recording_transcript_success_and_single_claim(self):
        job=self.job(); provider=Mock();provider.grade.return_value=GOOD
        self.assertTrue(process_job(job.pk,provider)); self.assertFalse(process_job(job.pk,provider))
        job.refresh_from_db();self.assertEqual(job.status,'ai_reviewed');self.assertIsNone(job.suggested_score)
        self.assertEqual(job.transcript,'My hobby is reading.');self.assertIsNone(job.result['pronunciation'])
        provider.grade.assert_called_once()

    def test_duplicate_callback_returns_same_job(self):
        self.assertEqual(self.job().pk,self.job().pk)
        self.assertEqual(GradingJob.objects.count(),1)

    def test_cross_task_key_rejected(self):
        self.job()
        with self.assertRaises(ValidationError):
            enqueue_submission(task=self.vocab_task,submission_key='s1',text='Customer')

    def test_client_cannot_override_rubric_kind_or_answers(self):
        response=self.post(self.student,kind='listening',reference_text='Give 10')
        self.assertEqual(response.status_code,201)
        job=GradingJob.objects.get();self.assertEqual(job.kind,'speaking')
        self.assertEqual(job.rubric_snapshot['reference_transcript'],'My hobby is reading.')
        self.assertEqual(job.rubric_snapshot['mode'],'repeat_video')

    def test_listening_uses_answer_key_without_ai(self):
        with patch('ai_core.services.OpenAIGrader') as api:
            job,_=enqueue_submission(task=self.listening_task,submission_key='listen',answers={str(self.q1.pk):'B',str(self.q2.pk):'B'})
            self.assertFalse(process_job(job.pk));api.assert_not_called()
        self.assertIsNone(job.final_score);self.assertEqual(job.status,'graded');self.assertEqual(job.grading_method,'answer_key')
        self.assertEqual(job.progress.responses.count(),2);self.assertIsNone(job.progress.score)

    def test_listening_missing_answer_is_zero_not_omitted(self):
        job,_=enqueue_submission(task=self.listening_task,submission_key='listen',answers={str(self.q1.pk):'B'})
        self.assertIsNone(job.final_score);self.assertEqual(job.result['total'],2)

    def test_listening_rejects_unknown_question(self):
        with self.assertRaises(ValidationError):
            enqueue_submission(task=self.listening_task,submission_key='bad',answers={'999999':'A'})
        self.assertEqual(GradingJob.objects.count(),0)

    def test_snapshot_survives_answer_edit(self):
        self.q1.correct_option='A';self.q1.save()
        job,_=enqueue_submission(task=self.listening_task,submission_key='old-key',answers={str(self.q1.pk):'B',str(self.q2.pk):'A'})
        self.assertIsNone(job.final_score)

    def test_vocabulary_missing_word_not_compensated_by_extra_repeats(self):
        job,_=enqueue_submission(task=self.vocab_task,submission_key='vocab',text='Customer Customer Customer Customer Customer Customer')
        provider=Mock();provider.grade.return_value={'needs_manual':False,'feedback':'Thiếu Deadline.','counts':[{'word':'Customer','count':6}]}
        process_job(job.pk,provider);job.refresh_from_db()
        self.assertIsNone(job.suggested_score);self.assertEqual(job.result['matched_total'],3)
        self.assertEqual(job.result['expected_total'],6);self.assertFalse(job.result['complete'])
        self.assertNotIn('handwriting',job.result)

    def test_vocab_complete_and_strict_count_validation(self):
        rubric=self.assignments['vocabulary'].rubric
        value={'needs_manual':False,'feedback':'Đủ lượt.','counts':[{'word':'customer','count':3},{'word':'Deadline','count':3}]}
        self.assertTrue(validate_result(value,'vocabulary',rubric)['complete'])
        for counts in [[{'word':'unknown','count':3}],[{'word':'Customer','count':True}],[{'word':'Customer','count':-1}],[{'word':'Customer','count':2},{'word':'Customer','count':2}]]:
            with self.assertRaises(ValueError):validate_result(dict(value,counts=counts),'vocabulary',rubric)

    def test_invalid_results_fall_back(self):
        for index,raw in enumerate([dict(GOOD,transcript=''),dict(GOOD,transcript=None),dict(GOOD,feedback=''),dict(GOOD,needs_manual=True),{},[]]):
            job=self.job(str(index));provider=Mock();provider.grade.return_value=raw
            process_job(job.pk,provider);job.refresh_from_db();self.assertEqual(job.status,'manual')

    def test_errors_timeout_no_exception_text_leaked(self):
        for index,error in enumerate([RuntimeError('secret-key'),TimeoutError()]):
            job=self.job(str(index));provider=Mock();provider.grade.side_effect=error
            process_job(job.pk,provider);job.refresh_from_db();self.assertEqual(job.status,'manual')
            self.assertNotIn('secret-key',job.fallback_reason)

    def test_watchdog_recovers_queued_and_crashed_jobs(self):
        for state in ['queued','processing']:
            job=self.job(state);GradingJob.objects.filter(pk=job.pk).update(status=state,submitted_at=self.now-timedelta(seconds=300))
        self.assertEqual(expire_jobs(self.now),2)
        provider=Mock();self.assertFalse(process_job(job.pk,provider));provider.grade.assert_not_called()

    def test_late_result_cannot_overwrite_manual(self):
        job=self.job();provider=Mock()
        def late(*args,**kwargs):
            GradingJob.objects.filter(pk=job.pk).update(status='manual');return GOOD
        provider.grade.side_effect=late;process_job(job.pk,provider);job.refresh_from_db()
        self.assertEqual(job.status,'manual');self.assertIsNone(job.suggested_score)

    def test_late_at_five_minutes_falls_back(self):
        job=self.job();provider=Mock();provider.grade.return_value=GOOD
        with patch('ai_core.services.timezone.now',side_effect=__import__('itertools').chain([job.submitted_at,job.submitted_at],__import__('itertools').repeat(job.ai_deadline))):process_job(job.pk,provider)
        job.refresh_from_db();self.assertEqual(job.status,'manual')

    def test_student_only_own_task_and_auth_required(self):
        self.assertEqual(self.client.post('/ai/submissions/',{},content_type='application/json').status_code,401)
        self.assertEqual(self.post(self.other_student).status_code,404)
        self.assertEqual(self.post(self.teacher).status_code,403)
        self.assertEqual(self.post(self.student).status_code,201)
        self.assertEqual(self.post(self.student).status_code,200)

    def test_review_permissions_and_duplicate_review(self):
        job=self.job();GradingJob.objects.filter(pk=job.pk).update(status='manual')
        url=f'/ai/jobs/{job.pk}/review/';body={'score':8,'feedback':'Đã kiểm tra.','completion_status':'complete'}
        for user,status in [(self.student,403),(self.manager,403),(self.other_teacher,404),(self.teacher,200)]:
            self.client.force_login(user);self.assertEqual(self.client.post(url,body,content_type='application/json').status_code,status)
        self.assertEqual(self.client.post(url,body,content_type='application/json').status_code,409)
        job.refresh_from_db();self.assertEqual(job.reviewed_by,self.teacher);self.assertIsNone(job.final_score)

    def test_csrf_submission_and_review(self):
        browser=Client(enforce_csrf_checks=True);browser.force_login(self.student)
        browser.get(f'/hoc-tap/tasks/{self.task.pk}/')
        data={'task_id':self.task.pk,'submission_key':'csrf'}
        self.assertEqual(browser.post('/ai/submissions/',dict(data,audio=self.audio())).status_code,403)
        self.assertEqual(browser.post('/ai/submissions/',dict(data,audio=self.audio()),HTTP_X_CSRFTOKEN=browser.cookies['csrftoken'].value).status_code,201)

    def test_invalid_submission_and_oversized_audio(self):
        for text in ['', 'a'*20001]:
            with self.assertRaises(ValidationError):enqueue_submission(task=self.task,submission_key='invalid',text=text)
        with self.assertRaises(ValidationError):
            enqueue_submission(task=self.task,submission_key='file',audio=SimpleUploadedFile('bad.exe',b'bad'))
        with override_settings(AI_MAX_AUDIO_BYTES=4), self.assertRaises(ValidationError):
            enqueue_submission(task=self.task,submission_key='too-large',audio=self.audio())

    def test_image_validation_and_private_access(self):
        stream=io.BytesIO();Image.new('RGB',(20,20),'white').save(stream,'PNG')
        with tempfile.TemporaryDirectory() as folder,override_settings(MEDIA_ROOT=folder):
            job,_=enqueue_submission(task=self.vocab_task,submission_key='image',images=[SimpleUploadedFile('page.png',stream.getvalue())])
            page=job.pages.get();url=f'/ai/pages/{page.pk}/'
            self.assertEqual(self.client.get(url).status_code,401)
            self.client.force_login(self.other_student);self.assertEqual(self.client.get(url).status_code,404)
            self.client.force_login(self.student);response=self.client.get(url);self.assertEqual(response.status_code,200);response.close()
            with self.assertRaises(ValidationError):enqueue_submission(task=self.vocab_task,submission_key='bad-img',images=[SimpleUploadedFile('fake.png',b'not an image')])

    @override_settings(OPENAI_API_KEY='test-not-real')
    def test_openai_adapter_transcribes_then_grades_text(self):
        with tempfile.TemporaryDirectory() as folder,override_settings(MEDIA_ROOT=folder):
            job,_=enqueue_submission(task=self.task,submission_key='audio',audio=SimpleUploadedFile('speech.webm',b'fake-test-audio'))
            with patch('openai.OpenAI') as factory:
                api=factory.return_value.__enter__.return_value;api.with_options.return_value=api
                api.audio.transcriptions.create.return_value=SimpleNamespace(text='I like books.')
                api.responses.create.return_value=SimpleNamespace(output_text=json.dumps(GOOD))
                result=OpenAIGrader().grade(job,120)
                self.assertEqual(result['transcript'],'I like books.')
                self.assertEqual(result['transcript_source'],'openai_transcription')
                api.audio.transcriptions.create.assert_called_once()
                self.assertEqual(api.audio.transcriptions.create.call_args.kwargs['languages'],['en'])
                self.assertNotIn('language',api.audio.transcriptions.create.call_args.kwargs)
                self.assertFalse(api.responses.create.call_args.kwargs['store'])
                self.assertNotIn('input_audio',str(api.responses.create.call_args))
                payload=json.loads(api.responses.create.call_args.kwargs['input'][0]['content'][0]['text'])
                self.assertEqual(payload['rubric']['reference_transcript'],'My hobby is reading.')
                self.assertEqual(payload['comparison'],result['comparison'])
                self.assertNotIn('prompt',api.audio.transcriptions.create.call_args.kwargs)

    @override_settings(OPENAI_API_KEY='test-not-real')
    def test_adapter_rejects_legacy_typed_text_instead_of_skipping_transcription(self):
        job=self.job()
        job.text='My hobby is reading.'
        with patch('openai.OpenAI') as factory:
            with self.assertRaises(ValueError):OpenAIGrader().grade(job,120)
            factory.assert_not_called()

    def test_student_cannot_submit_typed_transcript_even_with_audio(self):
        for with_audio in [False,True]:
            data={'task_id':self.task.pk,'submission_key':'typed','text':'My hobby is reading.'}
            if with_audio:data['audio']=self.audio()
            self.client.force_login(self.student)
            response=self.client.post('/ai/submissions/',data)
            self.assertEqual(response.status_code,400)
        self.assertFalse(GradingJob.objects.exists())

    def test_missing_video_reference_blocks_new_submission_and_legacy_queue_falls_back(self):
        assignment=self.assignments['speaking'];assignment.rubric={'skill':'speaking','prompts':['Introduce yourself.']};assignment.save()
        with self.assertRaises(ValidationError):self.job()
        legacy=GradingJob.objects.create(task=self.task,submission_key='legacy',kind='speaking',text='Hello',rubric_snapshot=assignment.rubric)
        provider=Mock();provider.grade.return_value=GOOD
        process_job(legacy.pk,provider);legacy.refresh_from_db();self.assertEqual(legacy.status,'manual')

    def test_server_does_not_use_model_score_for_reading_assessment(self):
        job=self.job();provider=Mock()
        provider.grade.return_value=dict(GOOD,transcript='My hobby is swimming.',score=10,content=10)
        process_job(job.pk,provider);job.refresh_from_db()
        self.assertIsNone(job.suggested_score)
        self.assertEqual(job.result['comparison']['different_words'],1)
        self.assertNotIn('content',job.result)

    def test_worker_once(self):
        job=self.job()
        with patch('ai_core.services.OpenAIGrader') as provider:
            provider.return_value.grade.return_value=GOOD;call_command('run_ai_worker',once=True)
        job.refresh_from_db();self.assertEqual(job.status,'ai_reviewed')

    def test_unreadable_vocabulary_routes_to_manual(self):
        job,_=enqueue_submission(task=self.vocab_task,submission_key='blurred',text='Unreadable')
        provider=Mock();provider.grade.return_value={'needs_manual':True,'feedback':'Không đọc rõ','counts':[]}
        process_job(job.pk,provider);job.refresh_from_db();self.assertEqual(job.status,'manual')

    def test_api_rejects_score_tampering_and_invalid_review(self):
        job=self.job();GradingJob.objects.filter(pk=job.pk).update(status='manual')
        self.client.force_login(self.teacher)
        for body in [{'score':True,'feedback':'x'},{'score':float('inf'),'feedback':'x'},{'score':11,'feedback':'x'},{'score':5,'feedback':''},[]]:
            self.assertEqual(self.client.post(f'/ai/jobs/{job.pk}/review/',body,content_type='application/json').status_code,400)

    def test_audio_private_access(self):
        with tempfile.TemporaryDirectory() as folder,override_settings(MEDIA_ROOT=folder):
            job,_=enqueue_submission(task=self.task,submission_key='private-audio',audio=SimpleUploadedFile('speech.wav',b'RIFF-test'))
            url=f'/ai/jobs/{job.pk}/audio/'
            self.assertEqual(self.client.get(url).status_code,401)
            self.client.force_login(self.other_teacher);self.assertEqual(self.client.get(url).status_code,404)
            self.client.force_login(self.student);response=self.client.get(url)
            self.assertEqual(response.status_code,200);self.assertIn('no-store',response['Cache-Control']);response.close()

    def test_duplicate_vocabulary_pages_rejected(self):
        stream=io.BytesIO();Image.new('RGB',(10,10),'white').save(stream,'PNG');raw=stream.getvalue()
        with self.assertRaises(ValidationError):
            enqueue_submission(task=self.vocab_task,submission_key='duplicates',images=[SimpleUploadedFile('a.png',raw),SimpleUploadedFile('b.png',raw)])
        self.assertFalse(GradingJob.objects.filter(submission_key='duplicates').exists())

    @override_settings(OPENAI_API_KEY='secret-test-do-not-print')
    def test_key_check_is_offline_and_never_prints_key(self):
        output=io.StringIO()
        with patch('openai.OpenAI') as factory:
            call_command('check_openai',stdout=output)
            factory.assert_not_called()
        self.assertNotIn('secret-test-do-not-print',output.getvalue())

    @override_settings(OPENAI_API_KEY='')
    def test_key_check_missing_key_gives_actionable_error(self):
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError):
            call_command('check_openai',stdout=io.StringIO())

    @override_settings(OPENAI_API_KEY='test-not-real')
    def test_transcription_preserved_when_grading_api_fails(self):
        with tempfile.TemporaryDirectory() as folder,override_settings(MEDIA_ROOT=folder):
            job,_=enqueue_submission(task=self.task,submission_key='transcript-fallback',audio=SimpleUploadedFile('clip.wav',b'RIFF-test'))
            with patch('openai.OpenAI') as factory:
                api=factory.return_value.__enter__.return_value;api.with_options.return_value=api
                api.audio.transcriptions.create.return_value=SimpleNamespace(text='This transcript was recovered.')
                api.responses.create.side_effect=RuntimeError('grading_failed')
                process_job(job.pk)
            job.refresh_from_db();self.assertEqual(job.status,'manual')
            self.assertEqual(job.transcript,'This transcript was recovered.')

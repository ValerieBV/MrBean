from unittest.mock import Mock
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from dashboard.testutils import IntegratedFixture
from dashboard.services import metrics_for
from .models import GradingJob
from .providers import validate_result
from .services import enqueue_submission, process_job


class CompletionAssessmentTests(IntegratedFixture):
    def test_speaking_completion_uses_assessment_not_transcript_similarity_or_model_score(self):
        job,_=enqueue_submission(task=self.task,submission_key='binary-speaking',audio=self.audio())
        provider=Mock()
        provider.grade.return_value={'needs_manual':False,'feedback':'Đã đọc đủ; transcript có thể nhận sai từ.',
            'transcript':'My hobby is swimming.','complete':True,'score':0}
        process_job(job.pk,provider);job.refresh_from_db()
        self.assertEqual(job.status,'ai_reviewed')
        self.assertTrue(job.result['complete'])
        self.assertEqual(job.result['comparison']['different_words'],1)
        self.assertNotIn('score',job.result)
        self.assertNotIn('score',job.result['comparison'])
        self.assertIsNone(job.suggested_score)
        self.assertEqual(job.completion_status,'pending')
        self.client.force_login(self.teacher)
        response=self.client.post(reverse('ai_core:review',args=[job.pk]),
            {'feedback':'Đã nghe và xác nhận làm đủ.','completion_status':'complete'},content_type='application/json')
        self.assertEqual(response.status_code,200)
        job.refresh_from_db();self.assertEqual(job.completion_status,'complete')
        self.assertIsNone(job.final_score)
        self.assertTrue(job.progress.is_completed)
        self.assertNotIn('final_score',response.json())
        self.assertNotIn('average_score',metrics_for(self.student))

    def test_uncertain_asr_does_not_become_an_incomplete_assessment(self):
        result=validate_result({'needs_manual':False,'feedback':'Chưa đủ bằng chứng.','complete':None,
            'transcript':'My hobby is swimming.'},'speaking',self.task.assignment.rubric)
        self.assertIsNone(result['complete'])
        self.assertNotIn('score',result)

    def test_vocabulary_counts_are_binary_and_missing_word_is_not_offset(self):
        rubric=self.vocab_task.assignment.rubric
        value={'needs_manual':False,'feedback':'Còn thiếu một từ.','score':10,
            'counts':[{'word':'Customer','count':6},{'word':'Deadline','count':0}]}
        result=validate_result(value,'vocabulary',rubric)
        self.assertFalse(result['complete']);self.assertNotIn('score',result)
        self.assertEqual(result['details'][1]['missing'],3)
        value['counts'][1]['count']=3
        self.assertTrue(validate_result(value,'vocabulary',rubric)['complete'])

    def test_listening_completion_does_not_require_correct_choices_but_requires_short_answers(self):
        questions=self.listening_task.assignment.rubric['questions']
        for key,short,complete in [('filled',True,True),('missing',False,False)]:
            answers={str(q['id']):{'chosen':'A' if q['correct_option']!='A' else 'B',
                'short_answer':'What I heard.' if short else ''} for q in questions}
            job,_=enqueue_submission(task=self.listening_task,submission_key=key,answers=answers)
            self.assertEqual(job.completion_status,'complete' if complete else 'incomplete')
            self.assertEqual(job.result['correct_count'],0)
            self.assertIsNone(job.final_score);self.assertNotIn('score',job.result)

    def test_range_requests_require_access_to_the_submission(self):
        job,_=enqueue_submission(task=self.task,submission_key='range-permission',
            audio=SimpleUploadedFile('recording.mp3',b'ID3-0123456789abcdef',content_type='audio/mpeg'))
        url=reverse('ai_core:audio',args=[job.pk])
        self.assertEqual(self.client.get(url,HTTP_RANGE='bytes=4-9').status_code,401)
        self.client.force_login(self.other_student)
        self.assertEqual(self.client.get(url,HTTP_RANGE='bytes=4-9').status_code,404)
        self.client.force_login(self.student)
        response=self.client.get(url,HTTP_RANGE='bytes=4-9')
        self.assertEqual(response.status_code,206)
        self.assertEqual(b''.join(response.streaming_content),b'012345')

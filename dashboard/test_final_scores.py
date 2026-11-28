"""Completion reporting never publishes or derives outcomes from legacy numeric grades."""
import csv
import io
import json
from datetime import timedelta
from django.urls import reverse
from ai_core.models import GradingJob
from ai_core.services import enqueue_submission
from dashboard.services import metrics_for
from dashboard.testutils import IntegratedFixture


class CompletionReportingTests(IntegratedFixture):
    def graded(self):
        return GradingJob.objects.create(task=self.task, submission_key='published',kind='speaking',status='graded',
            suggested_score=9.87,final_score=6.25,completion_status='complete',
            result={'score':9.87,'complete':True,'feedback':'Internal model feedback'},teacher_feedback='Teacher confirmed feedback',
            submitted_at=self.now-timedelta(hours=1))

    def pending(self, **extra):
        return GradingJob.objects.create(task=self.task,submission_key='unpublished',kind='speaking',status='ai_reviewed',
            suggested_score=9.99,result={'score':9.99,'complete':False,'feedback':'Internal draft feedback'},**extra)

    def assert_no_numeric_grading(self,data):
        if isinstance(data,dict):
            self.assertFalse({'score','final_score','suggested_score','average_score'} & data.keys())
            for value in data.values():self.assert_no_numeric_grading(value)
        elif isinstance(data,list):
            for value in data:self.assert_no_numeric_grading(value)

    def test_reports_keep_confirmed_completion_while_new_attempt_is_pending(self):
        old=self.graded();pending=self.pending()
        for user in [self.admin,self.manager,self.teacher,self.student]:
            data=metrics_for(user);self.assert_no_numeric_grading(data)
            row=next(x for x in data['tasks'] if x['id']==self.task.pk)
            self.assertEqual(row['completion_status'],'complete')
            self.assertTrue(row['resubmission_pending'])
            self.assertEqual(data['completed_count'],1)
            self.assertEqual(data['learner_progress'][0]['resubmissions_pending'],1)
            self.assertEqual(next(x for x in data['history'] if x['id']==pending.pk)['teacher_feedback'],'')
        old.refresh_from_db();self.assertEqual((old.final_score,old.suggested_score),(6.25,9.87))

    def test_pending_numeric_data_does_not_publish_completion(self):
        self.pending(final_score=9.1,teacher_feedback='Not published')
        data=metrics_for(self.student);self.assert_no_numeric_grading(data)
        self.assertEqual(data['completed_count'],0)
        self.assertTrue(all(x['teacher_feedback']=='' for x in data['history']))

    def test_dashboard_roles_do_not_have_score_cards_or_columns(self):
        for user in [self.admin,self.manager,self.teacher,self.student]:
            self.client.force_login(user);response=self.client.get(reverse('dashboard:index'))
            self.assertNotContains(response,'id="score"')
            self.assertNotContains(response,'Điểm cuối cùng')
            self.assertNotContains(response,'Điểm TB')
            self.assertContains(response,'Tiến độ hoàn thành')

    def test_csv_publishes_status_and_teacher_feedback_for_every_role(self):
        self.graded()
        for user in [self.admin,self.manager,self.teacher,self.student]:
            self.client.force_login(user);response=self.client.get(reverse('dashboard:export'))
            rows=list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
            self.assertEqual(rows[0][-2:],['Trạng thái','Nhận xét giáo viên'])
            row=next(row for row in rows[1:] if row[3]==self.task.title)
            self.assertEqual(row[-2:],['Hoàn thành','Teacher confirmed feedback'])
            self.assertNotIn('6.25',response.content.decode())
            self.assertNotIn('9.87',response.content.decode())

    def test_learner_result_and_api_show_final_completion_and_feedback(self):
        job=self.graded();self.client.force_login(self.student)
        response=self.client.get(reverse('submissions:result',args=[job.pk]))
        self.assertContains(response,'data-final-completion');self.assertContains(response,'Hoàn thành')
        self.assertContains(response,'Teacher confirmed feedback')
        self.assertNotContains(response,'data-ai-trial');self.assertNotContains(response,'data-final-score')
        self.assertNotContains(response,'Internal model feedback')
        data=self.client.get(reverse('ai_core:detail',args=[job.pk])).json()
        self.assert_no_numeric_grading(data);self.assertEqual(data['completion_status'],'complete')

    def test_teacher_confirms_without_score_and_can_override_the_ai_proposal(self):
        job=self.pending();self.client.force_login(self.teacher)
        response=self.client.post(reverse('ai_core:review',args=[job.pk]),
            {'feedback':'Final teacher assessment','completion_status':'complete'},content_type='application/json')
        self.assertEqual(response.status_code,200);self.assert_no_numeric_grading(response.json())
        job.refresh_from_db();self.assertIsNone(job.final_score)
        self.assertEqual(job.completion_status,'complete')
        response=self.client.get(reverse('submissions:result',args=[job.pk]))
        self.assertEqual(response.context['ai_trial']['complete'],False)
        self.assertEqual(response.context['published']['completion_status'],'complete')
        self.assertNotContains(response,'id="reviewForm"')

    def test_ai_trial_false_is_a_real_assessment_even_with_high_legacy_score(self):
        job=self.pending();self.client.force_login(self.teacher)
        response=self.client.get(reverse('submissions:result',args=[job.pk]))
        self.assertTrue(response.context['ai_trial']['available'])
        self.assertEqual(response.context['ai_trial']['label'],'Chưa hoàn thành')
        self.assertContains(response,'data-ai-trial-completion')
        self.assertNotContains(response,'data-ai-trial-score')
        self.assertNotContains(response,'9,99')

    def test_uncertain_ai_assessment_is_not_labeled_incomplete(self):
        job=self.pending();GradingJob.objects.filter(pk=job.pk).update(result={'complete':None,'feedback':'Cần nghe bản ghi.'})
        self.client.force_login(self.teacher)
        response=self.client.get(reverse('submissions:result',args=[job.pk]))
        self.assertEqual(response.context['ai_trial']['label'],'Cần giáo viên kiểm tra')
        self.assertIsNone(response.context['ai_trial']['complete'])

    def test_student_and_manager_never_receive_ai_assessment(self):
        job=self.graded()
        for user in [self.student,self.manager]:
            self.client.force_login(user);response=self.client.get(reverse('submissions:result',args=[job.pk]))
            self.assertNotContains(response,'data-ai-trial')
            self.assertContains(response,'Teacher confirmed feedback')

    def test_other_teacher_cannot_access_assessment_and_listening_has_no_ai_panel(self):
        job=self.pending();self.client.force_login(self.other_teacher)
        self.assertEqual(self.client.get(reverse('submissions:result',args=[job.pk])).status_code,404)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('submissions:result',args=[job.pk])),'data-ai-trial-completion')
        listening,_=enqueue_submission(task=self.listening_task,submission_key='answer-key',
            answers={str(self.q1.pk):'B',str(self.q2.pk):'A'})
        response=self.client.get(reverse('submissions:result',args=[listening.pk]))
        self.assertNotContains(response,'data-ai-trial')
        self.assertIsNone(listening.final_score)

    def test_pending_and_manual_jobs_have_no_ai_proposal(self):
        job=self.pending();self.client.force_login(self.teacher)
        for status in ['queued','processing','manual']:
            GradingJob.objects.filter(pk=job.pk).update(status=status)
            response=self.client.get(reverse('submissions:result',args=[job.pk]))
            self.assertFalse(response.context['ai_trial']['available'])
            self.assertContains(response,'data-ai-trial-empty')

    def test_legacy_score_without_completion_is_not_turned_into_a_pass(self):
        job=self.graded();GradingJob.objects.filter(pk=job.pk).update(completion_status='pending',result={'score':10,'feedback':'Old feedback'})
        data=metrics_for(self.student);self.assertEqual(data['completed_count'],0)
        self.client.force_login(self.teacher)
        response=self.client.get(reverse('submissions:result',args=[job.pk]))
        self.assertTrue(response.context['can_confirm_completion'])
        self.assertFalse(response.context['ai_trial']['available'])
        self.assertNotContains(response,'data-ai-trial-score')

    def test_ai_feedback_and_legacy_comparison_are_safe(self):
        job=self.pending();GradingJob.objects.filter(pk=job.pk).update(result={'complete':True,'feedback':'<script>alert("AI")</script>', 'comparison':{'score':9.9,'matched_words':4}})
        self.client.force_login(self.teacher)
        response=self.client.get(reverse('submissions:result',args=[job.pk]))
        self.assertNotContains(response,'<script>alert("AI")</script>')
        data=self.client.get(reverse('ai_core:detail',args=[job.pk])).json()
        self.assert_no_numeric_grading(data)

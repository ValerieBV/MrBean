import csv
import io
from datetime import timedelta
from django.urls import reverse
from ai_core.models import GradingJob
from dashboard.services import metrics_for
from dashboard.testutils import IntegratedFixture


class FinalScoreReportingTests(IntegratedFixture):
    def graded(self):
        return GradingJob.objects.create(task=self.task, submission_key='published', kind='speaking',
            status='graded', suggested_score=9.87, final_score=6.25,
            result={'score':9.87, 'feedback':'Internal model feedback'}, teacher_feedback='Teacher confirmed feedback',
            submitted_at=self.now-timedelta(hours=1))

    def pending(self, **extra):
        return GradingJob.objects.create(task=self.task, submission_key='unpublished', kind='speaking',
            status='ai_reviewed', suggested_score=9.99, result={'score':9.99, 'feedback':'Internal draft feedback'},
            **extra)

    def test_reports_use_only_confirmed_scores_after_resubmission(self):
        self.graded(); pending=self.pending()
        for user in [self.admin, self.manager, self.teacher, self.student]:
            with self.subTest(role=user.role):
                data=metrics_for(user)
                self.assertEqual(data['average_score'], 6.25)
                self.assertNotIn('average_ai_suggestion', data)
                row=next(x for x in data['tasks'] if x['id']==self.task.pk)
                self.assertEqual(row['final_score'], 6.25)
                self.assertNotIn('suggested_score', row)
                history=next(x for x in data['history'] if x['id']==pending.pk)
                self.assertIsNone(history['final_score'])
                self.assertEqual(history['teacher_feedback'], '')
                for section in ['history', 'graded_report', 'review_queue']:
                    for item in data[section]:
                        self.assertNotIn('suggested_score', item)
                        self.assertNotIn('result', item)
                        self.assertNotIn('AI', item['status_label'])
                self.assertEqual(data['learner_progress'][0]['average_score'], 6.25)

    def test_pending_submission_does_not_publish_a_score(self):
        self.pending(final_score=9.1, teacher_feedback='Not published')
        for user in [self.admin, self.manager, self.teacher, self.student]:
            data=metrics_for(user)
            self.assertIsNone(data['average_score'])
            self.assertTrue(all(x['final_score'] is None for x in data['tasks']))
            self.assertTrue(all(x['final_score'] is None for x in data['history']))
            self.assertEqual(data['graded_report'], [])

    def test_dashboard_cards_and_columns_follow_each_role(self):
        for user in [self.admin, self.manager, self.teacher, self.student]:
            with self.subTest(role=user.role):
                self.client.force_login(user)
                response=self.client.get('/dashboard/')
                self.assertContains(response, 'Điểm cuối cùng')
                self.assertNotContains(response, 'AI gợi ý')
                self.assertNotContains(response, 'aiScore')
                self.assertNotContains(response, 'duyệt AI')
                if user.role in ['admin', 'manager']:
                    self.assertNotContains(response, 'id="score"')
                    self.assertContains(response, 'class="stat"', count=2)
                else:
                    self.assertContains(response, 'id="score"')
                    self.assertContains(response, 'class="stat"', count=3)

    def test_csv_contains_one_published_score_column_for_all_roles(self):
        self.graded(); self.pending()
        for user in [self.admin, self.manager, self.teacher, self.student]:
            with self.subTest(role=user.role):
                self.client.force_login(user)
                response=self.client.get(reverse('dashboard:export'))
                rows=list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
                self.assertEqual(rows[0][-1], 'Điểm cuối cùng /10')
                self.assertEqual(len(rows[0]), 7)
                self.assertTrue(all(len(row)==7 for row in rows))
                self.assertNotIn('9.99', response.content.decode())
                self.assertNotIn('9.87', response.content.decode())
                row=next(row for row in rows[1:] if row[3]==self.task.title)
                self.assertEqual(row[-1], '6.25')

    def test_student_result_and_detail_expose_teacher_score_and_feedback(self):
        job=self.graded()
        self.client.force_login(self.student)
        response=self.client.get(reverse('submissions:result',args=[job.pk]))
        self.assertContains(response, 'Teacher confirmed feedback')
        self.assertContains(response, 'data-final-score')
        self.assertNotContains(response, 'AI gợi ý')
        self.assertNotContains(response, '9.87')
        self.assertNotContains(response, 'Internal model feedback')
        data=self.client.get(reverse('ai_core:detail',args=[job.pk])).json()
        self.assertEqual(data['final_score'], 6.25)
        self.assertEqual(data['teacher_feedback'], 'Teacher confirmed feedback')
        self.assertNotIn('suggested_score', data)
        self.assertNotIn('result', data)

    def test_pending_student_result_waits_for_teacher_confirmation(self):
        job=self.pending(final_score=9.1)
        self.client.force_login(self.student)
        response=self.client.get(reverse('submissions:result',args=[job.pk]))
        self.assertContains(response, 'Chờ giáo viên chấm')
        self.assertNotContains(response, '9.99')
        self.assertNotContains(response, '9.1')
        self.assertNotContains(response, 'Internal draft feedback')
        data=self.client.get(reverse('ai_core:detail',args=[job.pk])).json()
        self.assertIsNone(data['final_score'])
        self.assertNotIn('suggested_score', data)

    def test_teacher_confirmation_updates_published_report(self):
        job=self.pending()
        self.client.force_login(self.teacher)
        response=self.client.post(reverse('ai_core:review',args=[job.pk]),
            {'score':7.5, 'feedback':'Final teacher assessment'}, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        for user in [self.admin, self.manager, self.teacher, self.student]:
            self.client.force_login(user)
            data=self.client.get(reverse('dashboard:metrics')).json()
            self.assertEqual(data['average_score'], 7.5)
            self.assertEqual(data['graded_report'][0]['final_score'], 7.5)
            self.assertEqual(data['graded_report'][0]['teacher_feedback'], 'Final teacher assessment')
            self.assertNotIn('suggested_score', data['graded_report'][0])

    def test_listening_keeps_the_answer_key_final_grade(self):
        from ai_core.services import enqueue_submission
        job,_=enqueue_submission(task=self.listening_task, submission_key='answer-key',
            answers={str(self.q1.pk):'B',str(self.q2.pk):'A'})
        self.client.force_login(self.student)
        data=self.client.get(reverse('ai_core:detail',args=[job.pk])).json()
        self.assertEqual(data['final_score'], 10)
        self.assertEqual(metrics_for(self.student)['average_score'], 10)
        self.assertNotIn('suggested_score', data)

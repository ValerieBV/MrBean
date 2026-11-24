import csv
import io
import json
from datetime import timedelta
from unittest.mock import Mock

from django.urls import reverse
from django.utils import timezone
from accounts.models import CustomUser
from ai_core.models import GradingJob
from ai_core.services import enqueue_submission, process_job
from ai_core.tests import GOOD
from courses.models import Enrollment
from support.models import Conversation
from .models import LearningTask
from .services import metrics_for
from .testutils import IntegratedFixture


class InteractiveReportTests(IntegratedFixture):
    def setUp(self):
        super().setUp()
        self.student.first_name = self.other_student.first_name = 'Duplicate real name'
        self.student.student_code, self.other_student.student_code = 'A-01', 'B-02'
        self.student.save(); self.other_student.save()

    def data(self, **params):
        return self.client.get(reverse('dashboard:metrics'), params).json()

    def get_export(self, name='dashboard:export', args=None, **params):
        response = self.client.get(reverse(name, args=args), params)
        self.assertEqual(response.status_code, 200)
        return list(csv.DictReader(io.StringIO(response.content.decode('utf-8-sig'))))

    def test_ids_scope_overview_detail_metrics_and_export(self):
        for viewer, visible in [(self.admin, True), (self.manager, True), (self.teacher, True),
                                (self.other_teacher, False), (self.student, False), (self.other_student, False)]:
            self.client.force_login(viewer)
            for route in ('learner', 'learner_metrics', 'learner_export'):
                url = reverse('dashboard:' + route, args=[self.student.pk])
                self.assertEqual(self.client.get(url).status_code, 200 if visible else 404, (viewer.role, route))
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(reverse('dashboard:learner', args=[self.other_student.pk])).status_code, 404)
        self.client.force_login(self.manager)
        rows = self.get_export('dashboard:learner_export', [self.student.pk], skill='speaking')
        self.assertEqual([(r['Mã học viên'],r['Bài tập']) for r in rows], [('A-01',self.task.title)])
        self.assertNotIn(self.student.first_name, str(rows))
        self.assertEqual(self.client.get(reverse('dashboard:learner_metrics', args=[self.student.pk]),
                                          {'classroom': self.other_classroom.pk}).json()['assigned_count'], 0)

    def test_no_assignment_missing_and_duplicate_codes_are_navigable(self):
        with_no_tasks = CustomUser.objects.create_user('no_tasks', role='student', student_code='A-01')
        Enrollment.objects.create(student=with_no_tasks, classroom=self.classroom)
        # Enrolling directly does not create tasks until the roster is synchronized.
        with_no_tasks.learning_tasks.all().delete()
        self.client.force_login(self.teacher)
        people = self.data(q='A-01')['learner_progress']
        self.assertEqual(len(people), 2)
        self.assertEqual(len({r['student_code'] for r in people}), 2)
        for r in people:
            self.assertEqual(self.client.get(r['detail_url']).status_code, 200)
            self.assertEqual(self.data(q=r['student_code'])['learner_progress'][0]['learner_id'], r['learner_id'])
        self.assertEqual(next(r['assigned'] for r in people if r['learner_id']==with_no_tasks.pk), 0)
        self.student.student_code=''; self.student.save()
        data=self.data(q=f'HV#{self.student.pk}')
        self.assertEqual(data['learner_progress'][0]['student_code'], f'HV#{self.student.pk}')
        self.assertNotIn(self.student.first_name, json.dumps(data, ensure_ascii=False))
        self.assertNotIn('learner_name', json.dumps(data))

    def test_same_filters_drive_all_charts_queue_support_history_and_export(self):
        job=GradingJob.objects.create(task=self.task, kind='speaking', submission_key='review', status='manual',
                                      fallback_reason='ai_uncertain_evidence')
        GradingJob.objects.create(task=self.vocab_task, kind='vocabulary',submission_key='old-grade',
                                  status='graded',completion_status='complete')
        Conversation.objects.create(student=self.student, job=job, kind='knowledge', status='waiting',
            escalated_at=self.now, classroom=self.classroom, recipient=self.teacher, recipient_role='teacher')
        self.client.force_login(self.teacher)
        week=timezone.localdate(self.task.assigned_at)
        selection=dict(classroom=self.classroom.pk, skill='speaking', stage='review', focus='submitted',
                       ai='manual', week=(week-timedelta(days=week.weekday())).isoformat(), q='A-01')
        data=self.data(**selection)
        self.assertEqual((data['assigned_count'],data['review_queue_count'],data['support_count']), (1,1,1))
        self.assertEqual({r['task_id'] for r in data['history']}, {self.task.pk})
        for dimension in ('skill','stage','classroom','week'):
            self.assertEqual(sum(r['total'] for r in data['charts'][dimension]), 1)
        self.assertEqual(self.client.get(data['support_queue'][0]['detail_url']).status_code,200)
        self.assertEqual([r['Bài tập'] for r in self.get_export(**selection)], [self.task.title])
        empty=dict(selection,stage='complete')
        data=self.data(**empty)
        self.assertTrue(all(not rows for rows in data['charts'].values()))
        self.assertFalse(data['learner_progress'] or data['review_queue'] or data['history'] or data['support_queue'])
        self.assertEqual(self.get_export(**empty), [])
        self.client.force_login(self.manager)
        self.assertEqual(self.data()['support_count'], 0)
        self.client.force_login(self.student)
        self.assertNotIn('support_queue', self.data())
        self.assertNotIn('ai_operations', self.data())
        for route in ('metrics','export'):
            self.assertEqual(self.client.get(reverse('dashboard:'+route), {'ai':'manual'}).status_code,400)

    def test_waiting_is_not_learner_work_and_old_attempts_only_remain_in_history(self):
        older=GradingJob.objects.create(task=self.vocab_task, submission_key='superseded',kind='vocabulary',
                                         status='manual', submitted_at=self.now-timedelta(hours=2))
        GradingJob.objects.create(task=self.vocab_task, submission_key='finished',kind='vocabulary',status='graded',
                                  completion_status='complete')
        GradingJob.objects.create(task=self.task, submission_key='waiting',kind='speaking',status='ai_reviewed')
        self.client.force_login(self.teacher)
        data=self.data()
        self.assertEqual((data['review_queue_count'],data['action_count']), (1,1))
        self.assertNotIn(older.pk,[r['id'] for r in data['review_queue']])
        self.assertIn(older.pk,[r['id'] for r in data['history']])
        self.assertEqual({x['key']:x['total'] for x in data['charts']['stage']}, {'complete':1,'review':1,'todo':1})
        self.client.force_login(self.student)
        self.assertEqual([t['id'] for t in self.data()['next_tasks']], [self.listening_task.pk])

    def test_ai_timing_survives_human_confirmation_and_legacy_is_unknown(self):
        job,_=enqueue_submission(task=self.task, submission_key='fresh', audio=self.audio())
        provider=Mock(); provider.grade.return_value=GOOD
        process_job(job.pk, provider)
        job.refresh_from_db()
        self.assertIsNotNone(job.ai_assessed_at)
        GradingJob.objects.filter(pk=job.pk).update(submitted_at=self.now-timedelta(minutes=12),
            ai_assessed_at=self.now-timedelta(minutes=10), finished_at=self.now-timedelta(minutes=10))
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.post(reverse('ai_core:review',args=[job.pk]),
            {'feedback':'Đã kiểm tra.','completion_status':'complete'},content_type='application/json').status_code,200)
        job.refresh_from_db()
        self.assertEqual(job.ai_assessed_at, self.now-timedelta(minutes=10))
        self.assertEqual(job.ai_assessment_method, 'openai')
        self.assertGreater(job.completion_confirmed_at, job.ai_assessed_at)
        GradingJob.objects.create(task=self.vocab_task, submission_key='historic', kind='vocabulary', status='graded',
            completion_status='complete',finished_at=self.now, grading_method='teacher')
        ops=self.data()['ai_operations']
        self.assertEqual((ops['total'],ops['measured'],ops['timely_rate']), (2,1,100))
        self.assertEqual(self.data(ai='unknown')['tasks'][0]['id'], self.vocab_task.pk)

    def test_filtering_does_not_turn_recent_activity_into_inactivity(self):
        LearningTask.objects.filter(learner=self.student).update(assigned_at=self.now-timedelta(days=14),
                                                               due_at=self.now-timedelta(days=1))
        GradingJob.objects.create(task=self.task,kind='speaking',submission_key='recent',status='processing')
        self.client.force_login(self.teacher)
        self.assertEqual(self.data(skill='vocabulary')['at_risk_learners'], [])
        self.assertEqual(self.data(focus='overdue')['task_count'], 2)

    def test_pagination_never_changes_chart_or_export_totals(self):
        for i in range(17):
            LearningTask.objects.create(assignment_key=f'legacy-{i}', title=f'Archive {i}', learner=self.student,
                                        teacher=self.teacher, due_at=self.now)
        self.client.force_login(self.teacher)
        data=self.data(tasks_page='2')
        self.assertEqual((data['tasks_pagination']['total'],len(data['tasks'])),(20,8))
        self.assertEqual(sum(x['total'] for x in data['charts']['skill']),20)
        self.assertEqual(len(self.get_export(tasks_page='2')),20)
        self.assertEqual(self.data(classroom='legacy')['task_count'],17)

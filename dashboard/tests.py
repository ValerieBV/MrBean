from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from ai_core.models import GradingJob
from .models import LearningTask
from .services import metrics_for


class DashboardTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        User = get_user_model()
        self.teacher = User.objects.create_user(username='teacher', role='teacher')
        self.other = User.objects.create_user(username='other', role='teacher')
        self.manager = User.objects.create_user(username='manager', role='manager')
        self.student = User.objects.create_user(username='student', role='student')

    def task(self, key='a1', **kwargs):
        return LearningTask.objects.create(assignment_key=key, title=key, learner=self.student,
                                           teacher=kwargs.get('teacher', self.teacher),
                                           assigned_at=kwargs.get('assigned_at', self.now - timedelta(days=1)),
                                           due_at=kwargs.get('due_at', self.now - timedelta(hours=1)))

    def job(self, task, key, **kwargs):
        return GradingJob.objects.create(task=task, submission_key=key, kind='vocabulary', **kwargs)

    def test_empty_and_permissions(self):
        self.assertEqual(metrics_for(self.teacher, self.now)['submission_rate'], 0)
        self.assertIsNone(metrics_for(self.teacher, self.now)['average_score'])
        self.assertEqual(self.client.get('/dashboard/metrics/').status_code, 401)
        self.client.force_login(self.student)
        self.assertEqual(self.client.get('/dashboard/metrics/').status_code, 403)
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get('/dashboard/').status_code, 200)
        response = self.client.get('/dashboard/metrics/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response['Cache-Control'])

    def test_rate_unique_tasks_and_latest_final_score(self):
        first, second = self.task(), self.task('a2')
        self.job(first, '1', status='graded', final_score=2, submitted_at=self.now - timedelta(hours=2))
        self.job(first, '2', status='graded', final_score=8, submitted_at=self.now - timedelta(hours=1))
        self.job(first, '3', status='ai_reviewed', suggested_score=10, submitted_at=self.now)
        data = metrics_for(self.teacher, self.now)
        self.assertEqual(data['submission_rate'], 50)
        self.assertEqual(data['submitted_count'], 1)
        self.assertEqual(data['average_score'], 8)
        self.assertEqual(data['average_ai_suggestion'], 10)

    def test_sla_boundaries_and_confirmed_grade_excluded(self):
        task = self.task()
        for key, hours, status in [('green', 41.99, 'manual'), ('yellow', 42, 'manual'),
                                    ('red', 48, 'manual'), ('confirmed', 50, 'graded'), ('ai', 43, 'ai_reviewed')]:
            self.job(task, key, status=status, submitted_at=self.now - timedelta(hours=hours))
        data = metrics_for(self.teacher, self.now)
        flags = {item['submission_key']: item['flag'] for item in data['sla_alerts']}
        self.assertEqual(flags, {'yellow': 'yellow', 'red': 'red', 'ai': 'yellow'})

    def test_scope(self):
        task = self.task(teacher=self.other)
        self.job(task, 'secret', status='manual', submitted_at=self.now - timedelta(hours=44))
        self.assertEqual(metrics_for(self.teacher, self.now)['assigned_count'], 0)
        self.assertEqual(metrics_for(self.teacher, self.now)['sla_alerts'], [])
        self.assertEqual(metrics_for(self.manager, self.now)['assigned_count'], 1)

    def test_dropout_rules_and_recovery(self):
        for i in range(3):
            self.task(str(i))
        data = metrics_for(self.teacher, self.now)
        self.assertEqual(data['at_risk_learners'][0]['reason'], 'missed_tasks')
        task = LearningTask.objects.first()
        self.job(task, 'recovered', submitted_at=self.now)
        self.assertEqual(metrics_for(self.teacher, self.now)['at_risk_learners'], [])

    def test_inactivity_with_overdue_task(self):
        self.task(assigned_at=self.now - timedelta(days=7))
        self.assertEqual(metrics_for(self.teacher, self.now)['at_risk_learners'][0]['reason'], 'inactive')

    def test_future_assignment_and_new_learner_not_at_risk(self):
        self.task(assigned_at=self.now + timedelta(days=1), due_at=self.now + timedelta(days=2))
        self.assertEqual(metrics_for(self.teacher, self.now)['assigned_count'], 0)
        self.assertEqual(metrics_for(self.teacher, self.now)['at_risk_learners'], [])

    def test_progress_resubmission_keeps_confirmed_score(self):
        task = self.task()
        self.task('not-submitted')
        self.job(task, 'old-grade', status='graded', final_score=8, submitted_at=self.now-timedelta(hours=3), finished_at=self.now-timedelta(hours=2), reviewed_by=self.teacher, teacher_feedback='Good')
        self.job(task, 'new-attempt', status='manual', submitted_at=self.now)
        data = metrics_for(self.teacher, self.now)
        row = data['learner_progress'][0]
        self.assertEqual((row['assigned'], row['submitted'], row['not_submitted']), (2, 1, 1))
        self.assertEqual((row['awaiting_grade'], row['graded'], row['resubmissions_pending']), (1, 0, 1))
        self.assertEqual(row['average_score'], 8)
        self.assertEqual(data['graded_report'][0]['teacher_feedback'], 'Good')

    def test_late_history_survives_confirmation_and_is_scoped(self):
        task = self.task()
        self.job(task, 'late', status='graded', final_score=7, submitted_at=self.now-timedelta(hours=50), finished_at=self.now)
        self.job(task, 'on-time', status='graded', final_score=8, submitted_at=self.now-timedelta(hours=40), finished_at=self.now)
        data = metrics_for(self.teacher, self.now)
        self.assertEqual(data['sla_alerts'], [])
        self.assertEqual(data['sla_late_count'], 1)
        self.assertTrue(data['sla_late_report'][0]['sla_breached'])
        self.assertEqual(data['sla_late_report'][0]['hours_to_grade'], 50)
        self.assertEqual(metrics_for(self.other, self.now)['graded_report'], [])
        self.assertEqual(metrics_for(self.other, self.now)['learner_progress'], [])
        self.assertEqual(metrics_for(self.other, self.now)['sla_late_count'], 0)

    def test_roster_sync_includes_non_submitters_and_is_idempotent(self):
        from .integration import sync_assignment_roster
        another = get_user_model().objects.create_user(username='second', role='student')
        args = dict(assignment_key='synced', title='Lesson', teacher=self.teacher,
                    learners=[self.student, another, another], assigned_at=self.now-timedelta(days=1), due_at=self.now)
        tasks = sync_assignment_roster(**args)
        self.assertEqual(len(tasks), 2)
        self.job(tasks[0], 'submitted', submitted_at=self.now)
        sync_assignment_roster(**args)
        data = metrics_for(self.teacher, self.now)
        self.assertEqual(data['assigned_count'], 2)
        self.assertEqual(data['submission_rate'], 50)

    def test_roster_sync_cannot_reassign_history(self):
        from django.core.exceptions import ValidationError
        from .integration import sync_assignment_roster
        task = self.task()
        self.job(task, 'existing', submitted_at=self.now)
        with self.assertRaises(ValidationError):
            sync_assignment_roster(assignment_key='a1', title='Changed', teacher=self.other,
                                   learners=[self.student], assigned_at=self.now-timedelta(days=1), due_at=self.now)
        task.refresh_from_db()
        self.assertEqual(task.teacher, self.teacher)

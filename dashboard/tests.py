import io
from datetime import timedelta
from django.core.exceptions import ValidationError, PermissionDenied
from django.core.management import call_command
from django.utils import timezone
from django.test import override_settings
from dashboard.testutils import IntegratedFixture
from dashboard.models import LearningTask
from dashboard.integration import sync_class_assignment
from dashboard.services import metrics_for
from assignments.models import ClassAssignment, Lesson, ListeningQuestion
from assignments.services import assign_to_class
from courses.models import Enrollment
from accounts.models import CustomUser
from ai_core.models import GradingJob
from ai_core.services import enqueue_submission


class DashboardTests(IntegratedFixture):
    def test_roster_denominator_includes_non_submitters(self):
        data=metrics_for(self.teacher)
        self.assertEqual(data['assigned_count'],3);self.assertEqual(data['submission_rate'],0)
        enqueue_submission(task=self.listening_task,submission_key='listen',answers={str(self.q1.pk):'B',str(self.q2.pk):'A'})
        data=metrics_for(self.teacher);self.assertEqual(data['submitted_count'],1);self.assertEqual(data['submission_rate'],33.33)
        self.assertNotIn('average_score',data)

    def test_duplicate_submit_and_multiple_attempts_do_not_inflate_rate(self):
        enqueue_submission(task=self.task,submission_key='first',audio=self.audio())
        enqueue_submission(task=self.task,submission_key='first',audio=self.audio())
        enqueue_submission(task=self.task,submission_key='second',audio=self.audio())
        data=metrics_for(self.teacher);self.assertEqual(data['submitted_count'],1)
        self.assertEqual(data['learner_progress'][0]['awaiting_grade'],1)

    def test_resubmission_keeps_latest_confirmed_score(self):
        GradingJob.objects.create(task=self.task,submission_key='old',kind='speaking',status='graded',final_score=8,submitted_at=self.now-timedelta(hours=1),teacher_feedback='Official feedback')
        enqueue_submission(task=self.task,submission_key='new',audio=self.audio())
        data=metrics_for(self.teacher);row=data['learner_progress'][0]
        self.assertNotIn('average_score',row);self.assertEqual(row['resubmissions_pending'],1)
        self.assertEqual(row['graded'],0);self.assertEqual(row['awaiting_grade'],1)
        self.assertEqual(data['graded_report'][0]['teacher_feedback'],'Official feedback')

    def test_role_scoping_and_cross_class_filter(self):
        for user in [self.other_teacher,self.other_student]:
            data=metrics_for(user);self.assertEqual(data['assigned_count'],0);self.assertEqual(data['history'],[])
        self.assertEqual(metrics_for(self.student)['assigned_count'],3)
        self.assertEqual(metrics_for(self.manager)['assigned_count'],3)
        self.assertEqual(metrics_for(self.teacher,filters={'classroom':str(self.other_classroom.pk)})['assigned_count'],0)
        self.assertEqual(metrics_for(self.teacher,filters={'skill':'listening'})['assigned_count'],1)

    def test_three_dashboards_and_shared_nav(self):
        for user,title in [(self.admin,'Tổng quan quản lý'),(self.manager,'Tổng quan quản lý'),(self.teacher,'Lớp học và bài cần chấm'),(self.student,'Bài tập và kết quả của tôi')]:
            self.client.force_login(user);response=self.client.get('/dashboard/')
            self.assertEqual(response.status_code,200);self.assertContains(response,title)
            self.assertNotContains(response,'GIÁM SÁT SLA')
            self.assertEqual(self.client.get('/dashboard/metrics/').status_code,200)
        self.assertNotContains(response,'GIAO BÀI CHO LỚP')

    def test_student_result_privacy_and_html_escaping(self):
        job=GradingJob.objects.create(task=self.task,submission_key='xss',kind='speaking',transcript='<script>alert(1)</script>')
        self.client.force_login(self.other_student);self.assertEqual(self.client.get(f'/hoc-tap/results/{job.pk}/').status_code,404)
        self.client.force_login(self.student);response=self.client.get(f'/hoc-tap/results/{job.pk}/')
        self.assertEqual(response.status_code,200);self.assertContains(response,'&lt;script&gt;')
        self.assertNotContains(response,'<form id="reviewForm">')

    def test_metrics_no_sla_and_pagination(self):
        for index in range(30):
            GradingJob.objects.create(task=self.task,submission_key=str(index),kind='speaking',status='graded',final_score=5)
        data=metrics_for(self.teacher,filters={'history_page':'2','grades_page':'2'})
        self.assertEqual(data['history_pagination']['total'],30);self.assertEqual(len(data['history']),5)
        self.assertEqual(len(data['graded_report']),5);self.assertNotIn('sla_alerts',data)
        self.assertNotIn('sla_late_report',data)

    def test_dropout_rule_and_recovery(self):
        LearningTask.objects.filter(learner=self.student).update(due_at=self.now-timedelta(days=1))
        data=metrics_for(self.teacher);self.assertEqual(data['at_risk_learners'][0]['missed_tasks'],3)
        enqueue_submission(task=self.task,submission_key='recover',audio=self.audio())
        self.assertEqual(metrics_for(self.teacher)['at_risk_learners'],[])

    def test_new_enrollment_sync_includes_non_submitter(self):
        learner=CustomUser.objects.create_user(username='new_student',role='student')
        Enrollment.objects.create(classroom=self.classroom,student=learner)
        for assignment in self.assignments.values():sync_class_assignment(assignment)
        self.assertEqual(metrics_for(self.teacher)['assigned_count'],6)
        for assignment in self.assignments.values():sync_class_assignment(assignment)
        self.assertEqual(metrics_for(self.teacher)['assigned_count'],6)

    def test_create_assignment_requires_teacher_and_owned_class(self):
        new=Lesson.objects.create(skill='speaking',program='CHUNG',order=2,title='Next',description='Tell your story')
        with self.assertRaises(PermissionDenied):
            assign_to_class(actor=self.other_teacher,lesson=new,classroom=self.classroom,assigned_at=self.now,due_at=self.now+timedelta(days=1))
        with self.assertRaises(ValidationError):
            assign_to_class(actor=self.teacher,lesson=self.speaking,classroom=self.classroom,assigned_at=self.now,due_at=self.now+timedelta(days=1))
        self.assertEqual(ClassAssignment.objects.count(),3)

    def test_incomplete_listening_bank_cannot_be_assigned(self):
        lesson=Lesson.objects.create(skill='listening',program='CHUNG',order=2,title='No key')
        ListeningQuestion.objects.create(lesson=lesson,option_a='Answer')
        with self.assertRaises(ValidationError):
            assign_to_class(actor=self.teacher,lesson=lesson,classroom=self.classroom,assigned_at=self.now,due_at=self.now+timedelta(days=1))

    def test_student_cannot_open_staff_bank_or_other_task(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get('/quan-ly/bai-tap/').status_code,403)
        self.client.force_login(self.other_student)
        self.assertEqual(self.client.get(f'/hoc-tap/tasks/{self.task.pk}/').status_code,404)

    def test_student_listening_form_does_not_leak_correct_option(self):
        self.client.force_login(self.student);response=self.client.get(f'/hoc-tap/tasks/{self.listening_task.pk}/')
        self.assertEqual(response.status_code,200)
        self.assertNotContains(response,'correct_option');self.assertNotContains(response,'rubric_snapshot')
        self.assertContains(response,'Question1');self.assertContains(response,'b1')

    def test_all_assignment_templates_render(self):
        self.client.force_login(self.teacher)
        for url in ['/quan-ly/bai-tap/','/quan-ly/bai-tap/new/','/quan-ly/bai-tap/assign/',f'/quan-ly/bai-tap/lesson/{self.listening.pk}/']:
            self.assertEqual(self.client.get(url).status_code,200,url)

    @override_settings(DEBUG=True)
    def test_seed_is_idempotent_and_does_not_reset_password(self):
        call_command('seed_demo',password='DemoLocal123!',stdout=io.StringIO())
        user=CustomUser.objects.get(username='demo_student');old=user.password
        call_command('seed_demo',password='Different123!',stdout=io.StringIO())
        user.refresh_from_db();self.assertEqual(user.password,old)
        self.assertEqual(ClassAssignment.objects.filter(classroom__class_code='DEMO-01').count(),2)

    def test_import_legacy_listening_progress_is_idempotent(self):
        from submissions.models import LessonProgress
        progress=LessonProgress.objects.create(student=self.student,lesson=self.listening,status='completed',score=80,completed_at=self.now)
        args={'classroom':'C1','due_at':(self.now+timedelta(days=1)).isoformat(),'stdout':io.StringIO()}
        call_command('import_legacy_progress',**args)
        call_command('import_legacy_progress',**args)
        job=GradingJob.objects.get(submission_key=f'legacy-progress:{progress.pk}')
        self.assertEqual(job.final_score,8);self.assertEqual(job.progress,progress)
        self.assertEqual(job.grading_method,'legacy_import')

    def test_enrollment_service_adds_new_student_to_open_assignments(self):
        from courses.services import ClassManagementService
        learner=CustomUser.objects.create_user(username='added_later',role='student')
        ClassManagementService.enroll_student_to_class(self.classroom,learner)
        self.assertEqual(LearningTask.objects.filter(learner=learner).count(),3)
        self.assertEqual(metrics_for(self.teacher)['assigned_count'],6)

    def test_teacher_transfer_updates_scope_without_exposing_to_old_teacher(self):
        self.classroom.teacher=self.other_teacher;self.classroom.save()
        self.assertEqual(metrics_for(self.teacher)['assigned_count'],0)
        self.assertEqual(metrics_for(self.other_teacher)['assigned_count'],3)
        for assignment in self.assignments.values():
            assignment.classroom.refresh_from_db();sync_class_assignment(assignment)
        self.task.refresh_from_db();self.assertEqual(self.task.teacher,self.other_teacher)

    def test_inactive_enrollment_cannot_submit(self):
        Enrollment.objects.filter(classroom=self.classroom,student=self.student).update(status='dropped')
        self.client.force_login(self.student)
        self.assertEqual(self.client.post('/ai/submissions/',{'task_id':self.task.pk,'submission_key':'dropped','text':'Hi'},content_type='application/json').status_code,404)

    def test_future_assignment_hidden_and_submission_blocked(self):
        LearningTask.objects.filter(pk=self.task.pk).update(assigned_at=self.now+timedelta(days=1))
        self.assertEqual(metrics_for(self.student)['assigned_count'],2)
        self.client.force_login(self.student)
        response = self.client.get(f'/hoc-tap/tasks/{self.task.pk}/')
        self.assertContains(response, 'Bài tập sắp mở')
        self.assertNotContains(response, 'name="submission_key"')

    def test_manager_can_assign_but_other_teacher_cannot(self):
        self.client.force_login(self.manager)
        lesson=Lesson.objects.create(skill='speaking',program='CHUNG',order=3,title='Read along',
            youtube_url=self.speaking.youtube_url,reference_transcript='Read this sample sentence.')
        body={'lesson':lesson.pk,'classroom':self.classroom.pk,'assigned_at':self.now.isoformat(),
              'due_at':(self.now+timedelta(days=1)).isoformat(),'repetitions':1}
        self.assertEqual(self.client.post('/quan-ly/bai-tap/assign/',body).status_code,302)
        self.client.force_login(self.other_teacher)
        form=self.client.get('/quan-ly/bai-tap/assign/').context['form']
        self.assertNotIn(self.classroom,list(form.fields['classroom'].queryset))

    def test_date_filter_keeps_cohort_denominator(self):
        tomorrow=(self.now+timedelta(days=1)).date().isoformat()
        self.assertEqual(metrics_for(self.teacher,filters={'date_from':tomorrow})['assigned_count'],0)
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get('/dashboard/metrics/?date_from=not-a-date').status_code,400)

    def test_account_with_reporting_history_is_deactivated(self):
        self.client.force_login(self.admin)
        response=self.client.post(f'/accounts/users/{self.student.pk}/deactivate/')
        self.assertEqual(response.status_code,302)
        self.student.refresh_from_db();self.assertFalse(self.student.is_active)
        self.assertEqual(LearningTask.objects.filter(learner=self.student).count(),3)

    def test_review_does_not_show_a_numeric_input(self):
        job=GradingJob.objects.create(task=self.task,submission_key='fraction',kind='speaking',status='ai_reviewed',suggested_score=7.33)
        self.client.force_login(self.teacher)
        response=self.client.get(f'/hoc-tap/results/{job.pk}/')
        self.assertNotContains(response,'id="score"')
        self.assertContains(response,'name="completion_status"')

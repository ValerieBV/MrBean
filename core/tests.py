"""Workflow and authorization regression checks for the integrated application."""
import csv
import io
import json
from datetime import timedelta
from unittest.mock import Mock
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone
from accounts.models import CustomUser, Notification
from courses.models import Course, Enrollment, ExemptionRequest
from courses.services import ExemptionControlService as Exempt, ClassManagementService
from assignments.models import Lesson, ListeningQuestion, ClassAssignment
from assignments.services import assign_to_class
from dashboard.models import LearningTask
from dashboard.testutils import IntegratedFixture
from dashboard.services import metrics_for
from ai_core.models import GradingJob
from ai_core.services import enqueue_submission, process_job, notify_manual_jobs
from submissions.models import LessonProgress


class CompleteWorkflowTests(IntegratedFixture):
    def login(self,user):
        self.client.force_login(user)

    def post_json(self,url,data):
        return self.client.post(url,json.dumps(data),content_type='application/json')

    def exemption(self,task=None):
        task = task or self.task
        return Exempt.submit_exemption(self.student,self.classroom,
            assignment=task.assignment,reason='Em xin phép vắng buổi này vì bị ốm.')

    def next_lesson(self,skill='speaking',program='CHUNG'):
        lesson=Lesson.objects.create(skill=skill,program=program,order=2,title='Buổi tiếp theo',created_by=self.teacher,
            youtube_url='https://youtu.be/abcdefghijk',reference_transcript='Read this exact script.')
        if skill=='listening':
            ListeningQuestion.objects.create(lesson=lesson,question_text='Next?',option_a='Yes',correct_option='A')
        assignment=assign_to_class(actor=self.teacher,lesson=lesson,classroom=self.classroom,
            assigned_at=self.now-timedelta(hours=1),due_at=self.now+timedelta(days=1))
        return assignment.tasks.get(learner=self.student)

    def test_admin_teacher_student_workflow_from_account_to_result(self):
        self.login(self.admin)
        response=self.client.post(reverse('courses:course_create'),{'code':'B1-NEW','name':'B1 khóa mới','course_type':'B1','description':'Khóa mới'})
        self.assertEqual(response.status_code,302)
        course=Course.objects.get(code='B1-NEW')
        response=self.client.post(reverse('courses:class_create'),{'class_code':'B1-C3','name':'Lớp B1 mới',
            'course':course.pk,'teacher':self.teacher.pk,'is_active':'on'})
        self.assertEqual(response.status_code,302)
        room=course.classes.get()
        response=self.client.post(reverse('accounts:user_create'),{'username':'flow_student','email':'flow@example.test',
            'role':'student','student_code':'B2026Flow01','password':'Learning!8429','confirm_password':'Learning!8429'})
        self.assertEqual(response.status_code,302)
        learner=CustomUser.objects.get(username='flow_student')
        self.assertTrue(learner.check_password('Learning!8429'))
        self.assertEqual(self.client.post(reverse('courses:enroll_student',args=[room.pk]),{'student':learner.pk}).status_code,302)
        enrollment=Enrollment.objects.get(student=learner)
        self.assertEqual(enrollment.exemption_quota.max_quota,5)
        self.login(self.teacher)
        self.assertEqual(self.client.post(reverse('assignments:lesson_create'),{'skill':'vocabulary','program':'B1','order':1,
            'title':'B1 first words','description':'Chép mỗi từ 2 lần.','is_active':'on'}).status_code,302)
        lesson=Lesson.objects.get(title='B1 first words')
        self.assertEqual(self.client.post(reverse('assignments:lesson_detail',args=[lesson.pk]),
            {'order':1,'word':'Hello','meaning':'Xin chào'}).status_code,302)
        self.assertEqual(self.client.post(reverse('assignments:assign'),{'lesson':lesson.pk,'classroom':room.pk,
            'assigned_at':self.now.isoformat(),'due_at':(self.now+timedelta(days=2)).isoformat(),
            'repetitions':2,'allow_late_submission':'on','requires_previous':'on'}).status_code,302)
        task=LearningTask.objects.get(assignment__lesson=lesson,learner=learner)
        self.login(learner)
        response=self.post_json(reverse('ai_core:submit'),{'task_id':task.pk,'submission_key':'flow-vocab',
            'text':'Hello Hello','reference_version':task.assignment.reference_version})
        self.assertEqual(response.status_code,201,response.content)
        job=GradingJob.objects.get(pk=response.json()['id'])
        provider=Mock();provider.grade.return_value={'needs_manual':False,'feedback':'Đã chép đủ lượt.',
            'counts':[{'word':'Hello','count':2}]}
        process_job(job.pk,provider);job.refresh_from_db()
        self.assertEqual(job.status,'ai_reviewed');self.assertIsNone(job.suggested_score)
        self.assertIsNone(job.final_score)
        self.login(self.teacher)
        response=self.post_json(reverse('ai_core:review',args=[job.pk]),{'score':10,'feedback':'Hoàn thành tốt, giữ thói quen luyện tập.','completion_status':'complete'})
        self.assertEqual(response.status_code,200)
        self.login(learner)
        self.assertContains(self.client.get(reverse('submissions:result',args=[job.pk])),'Hoàn thành tốt')
        metrics=self.client.get(reverse('dashboard:metrics')).json()
        self.assertEqual((metrics['assigned_count'],metrics['submitted_count'],metrics['completed_count']),(1,1,1))
        self.assertTrue(learner.notifications.filter(event_key=f'result:{job.pk}').exists())
        self.assertContains(self.client.get(reverse('dashboard:export')),'B1 first words')

    def test_all_main_pages_render_for_each_role(self):
        common=['/dashboard/','/courses/','/courses/exemptions/','/accounts/notifications/','/accounts/profile/','/accounts/password/']
        staff=['/quan-ly/bai-tap/','/quan-ly/bai-tap/new/','/quan-ly/bai-tap/assign/','/quan-ly/bai-tap/assigned/',
            f'/quan-ly/bai-tap/assigned/{self.task.assignment_id}/',f'/quan-ly/bai-tap/assigned/{self.task.assignment_id}/edit/',
            f'/quan-ly/bai-tap/assigned/{self.task.assignment_id}/reading-reference/']
        admin=['/accounts/users/','/accounts/users/create/','/courses/catalog/','/courses/catalog/new/','/courses/classes/create/',
            f'/courses/enrollments/{Enrollment.objects.get(student=self.student).pk}/edit/']
        for user in [self.admin,self.manager,self.teacher,self.student]:
            self.login(user)
            urls=common+(staff if user.role!='student' else ['/hoc-tap/ky-nang/',f'/hoc-tap/tasks/{self.task.pk}/'])
            if user.role in ('admin','manager'):urls+=admin
            for url in urls:
                with self.subTest(role=user.role,url=url):self.assertEqual(self.client.get(url).status_code,200)

    def test_student_nav_has_no_staff_links_and_profile_cannot_promote(self):
        self.login(self.student)
        response=self.client.get('/dashboard/')
        self.assertNotContains(response,'href="/accounts/users/"')
        self.assertNotContains(response,'href="/quan-ly/bai-tap/')
        self.client.post('/accounts/profile/',{'first_name':'Changed','role':'admin','is_staff':'on'})
        self.student.refresh_from_db();self.assertEqual(self.student.role,'student');self.assertFalse(self.student.is_staff)
        self.assertEqual(self.client.get('/accounts/users/').status_code,403)

    def test_course_protection_and_class_archive_keep_history(self):
        job,_=enqueue_submission(task=self.listening_task,submission_key='archive',answers={str(self.q1.pk):'B'})
        self.login(self.admin)
        response=self.client.post(reverse('courses:course_delete',args=[self.classroom.course_id]),follow=True)
        self.assertContains(response,'Khóa học đã có lớp')
        response=self.client.post(reverse('courses:class_update',args=[self.classroom.pk]),{
            'class_code':'C1','name':'Class 1','course':self.classroom.course_id,'teacher':self.teacher.pk})
        self.assertEqual(response.status_code,302)
        self.assertEqual(Enrollment.objects.get(student=self.student).status,'completed')
        self.assertEqual(metrics_for(self.student)['assigned_count'],0)
        self.assertEqual(metrics_for(self.student,filters={'scope':'all'})['assigned_count'],3)
        self.login(self.student);self.assertEqual(self.client.get(reverse('submissions:result',args=[job.pk])).status_code,200)
        self.assertTrue(GradingJob.objects.filter(pk=job.pk).exists())

    def test_enrollment_completion_can_transfer_without_deleting_history(self):
        enrollment=Enrollment.objects.get(student=self.student)
        self.login(self.admin)
        self.client.post(reverse('courses:enrollment_update',args=[enrollment.pk]),{'status':'completed'})
        ClassManagementService.enroll_student_to_class(self.other_classroom,self.student)
        self.assertEqual(self.student.class_enrollments.count(),2)
        self.assertEqual(self.student.class_enrollments.filter(status='active').get().classroom,self.other_classroom)
        self.assertEqual(self.student.learning_tasks.count(),3)

    def test_database_rejects_second_active_enrollment(self):
        with self.assertRaises(IntegrityError),transaction.atomic():
            Enrollment.objects.create(student=self.student,classroom=self.other_classroom)

    def test_sequential_unlock_requires_confirmed_completion(self):
        task=self.next_lesson()
        self.login(self.student)
        self.assertContains(self.client.get(reverse('submissions:do_task',args=[task.pk])),'xác nhận hoàn thành các bài trước')
        with self.assertRaises(ValidationError):enqueue_submission(task=task,submission_key='locked',audio=self.audio())
        job,_=enqueue_submission(task=self.task,submission_key='prerequisite',audio=self.audio())
        with self.assertRaises(ValidationError):enqueue_submission(task=task,submission_key='still-locked',audio=self.audio())
        GradingJob.objects.filter(pk=job.pk).update(status='graded',final_score=7,completion_status='complete')
        self.assertEqual(enqueue_submission(task=task,submission_key='unlocked',audio=self.audio())[0].status,'queued')

    def test_other_program_does_not_lock_a_lesson(self):
        task=self.next_lesson(program='B1')
        self.assertEqual(enqueue_submission(task=task,submission_key='separate',audio=self.audio())[0].status,'queued')

    def test_exemption_approval_unlocks_next_and_updates_denominator_once(self):
        next_task=self.next_lesson()
        exemption=self.exemption()
        Exempt.approve_exemption(exemption.pk,self.teacher,note='Đồng ý.')
        self.task.refresh_from_db();self.assertEqual(self.task.exemption_id,exemption.pk)
        data=metrics_for(self.student)
        self.assertEqual((data['assigned_count'],data['exempt_count']),(3,1))
        enqueue_submission(task=next_task,submission_key='after-exemption',audio=self.audio())
        with self.assertRaises(ValidationError):Exempt.approve_exemption(exemption.pk,self.teacher)
        self.assertEqual(Enrollment.objects.get(student=self.student).exemption_quota.used_quota,1)

    def test_pending_exemption_blocks_submission_then_cancel_restores_it(self):
        exemption=self.exemption()
        with self.assertRaises(ValidationError):enqueue_submission(task=self.task,submission_key='pending',audio=self.audio())
        self.login(self.student)
        self.assertContains(self.client.get(reverse('submissions:do_task',args=[self.task.pk])),'Hủy đơn')
        self.assertEqual(self.client.get(reverse('courses:exemption_cancel',args=[exemption.pk])).status_code,405)
        self.client.post(reverse('courses:exemption_cancel',args=[exemption.pk]))
        self.assertEqual(enqueue_submission(task=self.task,submission_key='cancelled',audio=self.audio())[0].status,'queued')
        self.assertEqual(Enrollment.objects.get(student=self.student).exemption_quota.used_quota,0)

    def test_cannot_request_exemption_for_listening_submitted_or_other_class(self):
        self.login(self.student)
        url=reverse('courses:request_exemption',args=[self.classroom.pk])
        response=self.client.post(url,{'assignment':self.listening_task.assignment_id,'reason':'Xin miễn'})
        self.assertEqual(response.status_code,200);self.assertFalse(ExemptionRequest.objects.exists())
        enqueue_submission(task=self.task,submission_key='done',audio=self.audio())
        with self.assertRaises(ValidationError):self.exemption()
        self.assertEqual(self.client.get(reverse('courses:request_exemption',args=[self.other_classroom.pk])).status_code,404)

    def test_duplicate_requests_and_wrong_teacher_cannot_consume_quota(self):
        exemption=self.exemption()
        with self.assertRaises(ValidationError):self.exemption()
        with self.assertRaises(ValidationError):Exempt.approve_exemption(exemption.pk,self.other_teacher)
        self.assertEqual(Enrollment.objects.get(student=self.student).exemption_quota.used_quota,0)
        self.login(self.other_teacher)
        self.assertEqual(self.client.get(reverse('courses:exemption_review',args=[exemption.pk])).status_code,404)

    def test_exempt_and_dropped_learners_do_not_trigger_dropout_alert(self):
        LearningTask.objects.filter(learner=self.student).update(due_at=self.now-timedelta(days=9),assigned_at=self.now-timedelta(days=10))
        Exempt.approve_exemption(self.exemption().pk,self.teacher)
        Exempt.approve_exemption(self.exemption(self.vocab_task).pk,self.teacher)
        data=metrics_for(self.teacher)
        self.assertEqual(data['at_risk_learners'][0]['missed_tasks'],1)
        Enrollment.objects.filter(student=self.student).update(status='dropped')
        self.assertEqual(metrics_for(self.teacher,filters={'scope':'all'})['at_risk_learners'],[])

    def test_listening_autosave_restores_choices_without_answer_key(self):
        self.login(self.student)
        body={'answers':{str(self.q1.pk):'A'},'reference_version':self.listening_task.assignment.reference_version}
        response=self.post_json(reverse('submissions:autosave',args=[self.listening_task.pk]),body)
        self.assertEqual(response.status_code,200)
        progress=LessonProgress.objects.get(student=self.student,lesson=self.listening)
        self.assertEqual(progress.status,'in_progress');self.assertFalse(self.listening_task.jobs.exists())
        response=self.client.get(reverse('submissions:do_task',args=[self.listening_task.pk]))
        self.assertContains(response,'value="A" checked');self.assertNotContains(response,'correct_option')
        body['answers']={'999999':'B'}
        self.assertEqual(self.post_json(reverse('submissions:autosave',args=[self.listening_task.pk]),body).status_code,400)
        self.assertEqual(self.post_json(reverse('submissions:autosave',args=[self.task.pk]),{'text':'typed'}).status_code,400)

    def test_expired_draft_and_stale_reference_are_rejected(self):
        self.login(self.student)
        self.vocab_task.draft = {'text': 'OLD DRAFT'}
        self.vocab_task.draft_saved_at = self.now - timedelta(hours=25)
        self.vocab_task.save(update_fields=['draft', 'draft_saved_at'])
        self.assertNotContains(self.client.get(reverse('submissions:do_task',args=[self.vocab_task.pk])),'OLD DRAFT')
        response=self.post_json(reverse('submissions:autosave',args=[self.vocab_task.pk]),{'text':'New','reference_version':'old'})
        self.assertEqual(response.status_code,400)
        with self.assertRaises(ValidationError):enqueue_submission(task=self.vocab_task,submission_key='stale',text='Customer',reference_version='old')

    def test_late_closed_paused_and_reopened_assignment(self):
        self.login(self.teacher)
        assignment=self.task.assignment
        past=self.now-timedelta(hours=2)
        self.client.post(reverse('assignments:assigned_update',args=[assignment.pk]),{'due_at':past.isoformat(),'is_active':'on'})
        self.task.refresh_from_db();self.assertEqual(self.task.due_at,past)
        with self.assertRaises(ValidationError):enqueue_submission(task=self.task,submission_key='closed',audio=self.audio())
        self.client.post(reverse('assignments:assigned_update',args=[assignment.pk]),{'due_at':past.isoformat(),'allow_late_submission':'on'})
        with self.assertRaises(ValidationError):enqueue_submission(task=self.task,submission_key='paused',audio=self.audio())
        self.client.post(reverse('assignments:assigned_update',args=[assignment.pk]),{'due_at':past.isoformat(),'is_active':'on','allow_late_submission':'on'})
        self.assertEqual(enqueue_submission(task=self.task,submission_key='reopened',audio=self.audio())[0].status,'queued')

    def test_video_upload_snapshot_stays_private_and_old_job_keeps_old_reference(self):
        self.login(self.teacher)
        url=reverse('assignments:reading_reference',args=[self.task.assignment_id])
        response=self.client.post(url,{'reference_transcript':'My hobby is reading.',
            'video_file':SimpleUploadedFile('sample.mp4',b'test-private-video',content_type='video/mp4')})
        self.assertEqual(response.status_code,302)
        assignment=ClassAssignment.objects.get(pk=self.task.assignment_id)
        self.assertTrue(assignment.rubric['video_name'].endswith('.mp4'))
        self.task.refresh_from_db()
        job,_=enqueue_submission(task=self.task,submission_key='file-reference',audio=self.audio())
        old_version=assignment.reference_version
        self.client.post(url,{'reference_transcript':'New exact reference script.', 'youtube_url':'https://youtu.be/abcdefghijk'})
        job.refresh_from_db();self.assertEqual(job.rubric_snapshot['reference_transcript'],'My hobby is reading.')
        self.assertTrue(job.rubric_snapshot['video_name'])
        self.login(self.other_student)
        self.assertEqual(self.client.get(reverse('ai_core:reference_video',args=[job.pk])).status_code,404)
        self.login(self.student)
        response=self.client.get(reverse('ai_core:reference_video',args=[job.pk]))
        self.assertEqual(response.status_code,200);self.assertIn('private',response['Cache-Control']);response.close()
        self.assertEqual(self.client.get('/media/'+job.rubric_snapshot['video_name']).status_code,404)
        with self.assertRaises(ValidationError):enqueue_submission(task=self.task,submission_key='stale-video',audio=self.audio(),reference_version=old_version)

    def test_published_bank_cannot_be_deleted_but_clone_can_be_edited(self):
        self.login(self.teacher)
        self.client.post(reverse('assignments:lesson_delete',args=[self.listening.pk]))
        self.assertTrue(Lesson.objects.filter(pk=self.listening.pk).exists())
        response=self.client.post(reverse('assignments:lesson_clone',args=[self.listening.pk]))
        self.assertEqual(response.status_code,302)
        clone=Lesson.objects.filter(skill='listening',order=2).get()
        self.assertEqual(clone.questions.count(),2)
        self.assertFalse(clone.class_assignments.exists())
        item=clone.questions.first()
        response=self.client.post(reverse('assignments:item_edit',args=['listening',item.pk]),{
            'order':1,'question_text':'Changed question','option_a':'Changed','correct_option':'A'})
        self.assertEqual(response.status_code,302)
        self.q1.refresh_from_db();self.assertEqual(self.q1.question_text,'Question1')
        self.client.post(reverse('assignments:item_delete',args=['listening',item.pk]))
        self.assertEqual(clone.questions.count(),1)
        self.client.post(reverse('assignments:lesson_delete',args=[clone.pk]))
        self.assertFalse(Lesson.objects.filter(pk=clone.pk).exists())

    def test_cross_teacher_cannot_edit_assignment_or_bank_item(self):
        self.login(self.other_teacher)
        self.assertEqual(self.client.get(reverse('assignments:assigned_update',args=[self.task.assignment_id])).status_code,404)
        self.assertEqual(self.client.get(reverse('assignments:item_edit',args=['listening',self.q1.pk])).status_code,403)

    def test_notification_post_only_privacy_dedup_and_open(self):
        job,_=enqueue_submission(task=self.task,submission_key='fallback-event',audio=self.audio())
        GradingJob.objects.filter(pk=job.pk).update(status='manual')
        notify_manual_jobs();notify_manual_jobs()
        self.assertEqual(Notification.objects.filter(event_key=f'manual:{job.pk}').count(),1)
        item=Notification.objects.get(event_key=f'manual:{job.pk}')
        self.login(self.student)
        url=reverse('accounts:notification_read',args=[item.pk])
        self.assertEqual(self.client.post(url).status_code,404)
        self.login(self.teacher)
        self.assertEqual(self.client.get(url).status_code,405)
        self.assertRedirects(self.client.post(url,{'open':'1'}),reverse('submissions:result',args=[job.pk]))
        item.refresh_from_db();self.assertTrue(item.is_read)

    def test_logout_requires_csrf_post_and_profile_password_update_keeps_session(self):
        self.student.set_password('OriginalPass!882');self.student.save()
        self.login(self.student)
        self.assertEqual(self.client.get('/accounts/logout/').status_code,405)
        strict=Client(enforce_csrf_checks=True);strict.force_login(self.student)
        self.assertEqual(strict.post('/accounts/logout/').status_code,403)
        response=self.client.post('/accounts/password/',{'old_password':'OriginalPass!882','new_password1':'FreshPassword!994','new_password2':'FreshPassword!994'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(self.client.get('/accounts/profile/').status_code,200)
        self.student.refresh_from_db();self.assertTrue(self.student.check_password('FreshPassword!994'))

    def test_manager_cannot_create_admin_and_weak_password_is_rejected(self):
        self.login(self.manager)
        body={'username':'privileged','role':'admin','password':'StrongPass!811','confirm_password':'StrongPass!811'}
        self.assertEqual(self.client.post('/accounts/users/create/',body).status_code,200)
        self.assertFalse(CustomUser.objects.filter(username='privileged').exists())
        body.update(role='student',password='password123',confirm_password='password123')
        self.client.post('/accounts/users/create/',body)
        self.assertFalse(CustomUser.objects.filter(username='privileged').exists())

    def test_last_admin_and_active_teacher_deactivation_are_blocked(self):
        self.login(self.admin)
        self.client.post(reverse('accounts:user_deactivate',args=[self.admin.pk]))
        self.client.post(reverse('accounts:user_deactivate',args=[self.teacher.pk]))
        self.admin.refresh_from_db();self.teacher.refresh_from_db()
        self.assertTrue(self.admin.is_active);self.assertTrue(self.teacher.is_active)

    def test_csv_scoped_and_formula_values_escaped(self):
        self.student.first_name='=DANGEROUS';self.student.save()
        self.login(self.student)
        response=self.client.get(reverse('dashboard:export'))
        self.assertEqual(response.status_code,200)
        self.assertIn("'=DANGEROUS",response.content.decode())
        self.assertNotIn(self.other_student.username,response.content.decode())
        self.assertEqual(self.client.get(reverse('dashboard:export')+'?classroom=invalid').status_code,400)
        self.assertEqual(self.client.get(reverse('dashboard:metrics')+'?date_from=2026-12-01&date_to=2026-01-01').status_code,400)

    def test_old_member_b_routes_use_real_enrollment_and_shared_rules(self):
        self.login(self.student)
        self.assertRedirects(self.client.get(reverse('submissions:do_lesson',args=[self.listening.pk])),reverse('submissions:do_task',args=[self.listening_task.pk]))
        self.assertEqual(self.client.get(reverse('submissions:enter_class',args=[self.other_classroom.class_code])).status_code,404)
        response=self.post_json(reverse('submissions:submit_lesson',args=[self.listening.pk]),{'submission_key':'legacy-alias','answers':{str(self.q1.pk):'B',str(self.q2.pk):'A'}})
        self.assertEqual(response.status_code,201);self.assertNotIn('final_score',response.json())
        response=self.post_json(reverse('submissions:submit_lesson',args=[self.speaking.pk]),{'submission_key':'typed-alias','text':'Typed transcript'})
        self.assertEqual(response.status_code,400)

    @override_settings(DEBUG=True)
    def test_source_catalog_is_repeatable_and_never_overwrites_occupied_slots(self):
        title=self.vocab.title
        for _ in range(2):call_command('seed_source_catalog',owner=self.admin.username,stdout=io.StringIO())
        self.vocab.refresh_from_db();self.assertEqual(self.vocab.title,title)
        self.assertEqual(self.vocab.words.count(),2)
        source=Lesson.objects.get(skill='speaking',program='B1',order=1)
        self.assertFalse(source.is_active);self.assertEqual(source.speaking_tasks.count(),2)
        self.assertEqual(Course.objects.filter(code='ENG-B1').count(),1)
        self.login(self.admin)
        self.assertEqual(self.client.get('/courses/').status_code,200)
        self.assertEqual(self.client.get(reverse('courses:class_detail',args=[Course.objects.get(code='ENG-B1').classes.get().pk])).status_code,200)

    def test_nullable_source_authors_and_cancelled_reviewers_render(self):
        self.vocab.created_by=None;self.vocab.save(update_fields=['created_by'])
        self.login(self.teacher)
        self.assertEqual(self.client.get('/quan-ly/bai-tap/').status_code,200)
        item=self.exemption();Exempt.cancel(item.pk,self.student)
        self.login(self.student)
        self.assertEqual(self.client.get('/courses/exemptions/').status_code,200)

    @override_settings(DEBUG=True)
    def test_original_django_admin_lists_render_with_draft_source_data(self):
        root=CustomUser.objects.create_superuser(username='technical_root',password='RootOnly!7832')
        call_command('seed_source_catalog',owner=root.username,stdout=io.StringIO())
        self.exemption()
        self.login(root)
        for model in ['courses/classroom','courses/enrollment','courses/exemptionrequest',
            'courses/studentexemptionquota','accounts/customuser','assignments/lesson','ai_core/gradingjob']:
            with self.subTest(model=model):self.assertEqual(self.client.get('/admin/'+model+'/').status_code,200)

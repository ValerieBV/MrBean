from datetime import timedelta
from unittest.mock import Mock
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from dashboard.testutils import IntegratedFixture
from dashboard.services import metrics_for, annotated_tasks
from assignments.models import Lesson
from assignments.services import assign_to_class
from ai_core.models import GradingJob
from ai_core.services import enqueue_submission, process_job
from submissions.access import is_unlocked
from submissions.models import LessonProgress


class CompletionTests(IntegratedFixture):
    def submit(self, key='recording'):
        return enqueue_submission(task=self.task, submission_key=key, audio=self.audio())[0]

    def review(self, job, completion='complete', score=7.5):
        GradingJob.objects.filter(pk=job.pk).update(status='manual')
        self.client.force_login(self.teacher)
        response=self.client.post(reverse('ai_core:review',args=[job.pk]),
            {'score':score,'feedback':'Đã kiểm tra bài làm gốc.','completion_status':completion},
            content_type='application/json')
        self.assertEqual(response.status_code,200,response.content)
        job.refresh_from_db()
        return job

    def next_task(self):
        lesson=Lesson.objects.create(skill='speaking', program='CHUNG', order=2, title='Buổi tiếp theo',
            youtube_url=self.speaking.youtube_url, reference_transcript='I am learning.',created_by=self.teacher)
        assignment=assign_to_class(actor=self.teacher,lesson=lesson,classroom=self.classroom,
            assigned_at=self.now-timedelta(hours=1),due_at=self.now+timedelta(days=1),requires_previous=True)
        return assignment.tasks.get(learner=self.student)

    def listening_answers(self, *, short=True, correct=True):
        return {str(q.pk):{'chosen':q.correct_option if correct else ('A' if q.correct_option!='A' else 'B'),
            'short_answer':'The words I heard.' if short else ''} for q in [self.q1,self.q2]}

    def test_submission_and_ai_review_do_not_mark_completed(self):
        job=self.submit()
        self.assertEqual(job.progress.status,'submitted')
        self.assertIsNone(job.progress.completed_at)
        self.assertEqual(metrics_for(self.student)['completed_count'],0)
        provider=Mock()
        provider.grade.return_value={'needs_manual':False,'feedback':'Đã đọc đủ.','transcript':self.speaking.reference_transcript,'complete':True}
        process_job(job.pk,provider)
        job.refresh_from_db()
        self.assertEqual(job.status,'ai_reviewed')
        self.assertEqual(job.completion_status,'pending')
        self.assertEqual(metrics_for(self.student)['completed_count'],0)
        self.assertFalse(job.progress.is_completed)

    def test_completion_is_independent_of_numeric_score(self):
        job=self.review(self.submit(),completion='complete',score=6.5)
        self.assertEqual(job.progress.status,'completed')
        data=metrics_for(self.student)
        self.assertEqual(data['completed_count'],1)
        self.assertEqual(data['completion_rate'],33.33)
        self.assertEqual(data['average_score'],6.5)

    def test_incomplete_even_at_ten_points_does_not_unlock_next_lesson(self):
        next_task=self.next_task()
        self.assertFalse(is_unlocked(next_task))
        job=self.review(self.submit(),completion='incomplete',score=10)
        self.assertEqual(job.progress.status,'incomplete')
        self.assertIsNone(job.progress.completed_at)
        self.assertFalse(is_unlocked(next_task))
        data=metrics_for(self.student)
        self.assertEqual(data['incomplete_count'],1)
        self.assertEqual(data['completed_count'],0)
        self.assertEqual(next(x for x in data['tasks'] if x['id']==self.task.pk)['latest_status'],'incomplete')

    def test_only_final_complete_or_exemption_unlocks(self):
        next_task=self.next_task()
        first=self.submit()
        self.assertFalse(is_unlocked(next_task))
        self.review(first,'complete',score=5)
        self.assertTrue(is_unlocked(next_task))
        new=self.submit('new-attempt')
        self.assertTrue(is_unlocked(next_task))
        self.assertEqual(metrics_for(self.student)['completed_count'],1)
        self.review(new,'incomplete',score=8)
        self.assertFalse(is_unlocked(next_task))
        self.assertEqual(metrics_for(self.student)['completed_count'],0)

    def test_listening_wrong_choices_still_complete_when_all_fields_are_filled(self):
        job,_=enqueue_submission(task=self.listening_task,submission_key='wrong-but-done',
            answers=self.listening_answers(correct=False))
        self.assertEqual(job.final_score,0)
        self.assertEqual(job.completion_status,'complete')
        self.assertEqual(job.progress.status,'completed')
        self.assertEqual(metrics_for(self.student)['completed_count'],1)
        self.assertTrue(all(r.filled_text for r in job.progress.responses.all()))

    def test_listening_correct_choices_without_short_answers_are_incomplete(self):
        job,_=enqueue_submission(task=self.listening_task,submission_key='missing-short',
            answers=self.listening_answers(short=False))
        self.assertEqual(job.final_score,10)
        self.assertEqual(job.completion_status,'incomplete')
        self.assertEqual(job.result['missing_count'],2)
        self.assertEqual(job.progress.status,'incomplete')
        self.assertEqual(metrics_for(self.student)['completed_count'],0)

    def test_invalid_choice_nested_text_and_foreign_ids_are_rejected(self):
        for answers in [{str(self.q1.pk):{'chosen':'E','short_answer':'x'}},
                {str(self.q1.pk):{'chosen':'A','short_answer':9}},
                {str(self.q1.pk):{'chosen':'A','short_answer':'x'*256}},
                {'99999':{'chosen':'A','short_answer':'x'}}, []]:
            with self.subTest(answers=str(answers)[:60]), self.assertRaises(ValidationError):
                enqueue_submission(task=self.listening_task,submission_key='bad',answers=answers)

    def test_short_answers_are_saved_in_draft_and_restored_with_choice(self):
        self.client.force_login(self.student)
        body={'answers':self.listening_answers(),'text':'','reference_version':self.listening_task.assignment.reference_version}
        response=self.client.post(reverse('submissions:autosave',args=[self.listening_task.pk]),body,content_type='application/json')
        self.assertEqual(response.status_code,200,response.content)
        page=self.client.get(reverse('submissions:do_task',args=[self.listening_task.pk]))
        self.assertContains(page,'The words I heard.',count=2)
        self.assertContains(page,'checked',count=2)
        self.assertEqual(metrics_for(self.student)['completed_count'],0)
        row=next(x for x in metrics_for(self.student)['tasks'] if x['id']==self.listening_task.pk)
        self.assertEqual(row['latest_status'],'in_progress')

    def test_unknown_historical_completion_requires_confirmation_without_changing_grade(self):
        job=self.submit()
        reviewed_at=self.now-timedelta(minutes=1)
        GradingJob.objects.filter(pk=job.pk).update(status='graded',final_score=8.2,
            teacher_feedback='Nhận xét cũ.',reviewed_by=self.teacher,finished_at=reviewed_at)
        url=reverse('ai_core:confirm_completion',args=[job.pk])
        self.assertEqual(metrics_for(self.student)['completed_count'],0)
        for user,status in [(self.manager,403),(self.student,403),(self.other_teacher,404),(self.teacher,200)]:
            self.client.force_login(user)
            self.assertEqual(self.client.post(url,{'completion_status':'complete'},content_type='application/json').status_code,status)
        self.assertEqual(self.client.post(url,{'completion_status':'complete'},content_type='application/json').status_code,409)
        job.refresh_from_db()
        self.assertEqual((job.final_score,job.teacher_feedback,job.reviewed_by,job.finished_at),
            (8.2,'Nhận xét cũ.',self.teacher,reviewed_at))
        self.assertEqual(job.completion_confirmed_by,self.teacher)
        self.assertEqual(metrics_for(self.student)['completed_count'],1)

    def test_review_requires_explicit_completion_and_published_student_data_excludes_ai(self):
        job=self.submit()
        GradingJob.objects.filter(pk=job.pk).update(status='manual')
        self.client.force_login(self.teacher)
        url=reverse('ai_core:review',args=[job.pk])
        for flag in [None,'pending',True,10]:
            data={'score':9,'feedback':'Đã xem.'}
            if flag is not None:data['completion_status']=flag
            self.assertEqual(self.client.post(url,data,content_type='application/json').status_code,400)
        self.review(job,'complete',score=6)
        self.client.force_login(self.student)
        public=self.client.get(reverse('ai_core:detail',args=[job.pk])).json()
        self.assertEqual(public['completion_status'],'complete')
        self.assertEqual(public['status_label'],'Hoàn thành')
        self.assertNotIn('result',public);self.assertNotIn('suggested_score',public)

    def test_completion_before_deadline_uses_submission_time_not_teacher_delay(self):
        job=self.review(self.submit(),'complete',score=7)
        GradingJob.objects.filter(pk=job.pk).update(finished_at=self.task.due_at+timedelta(days=1))
        data=metrics_for(self.student,now=self.task.due_at+timedelta(days=2))
        self.assertEqual(data['completed_count'],1)
        self.assertEqual(data['on_time_completed_count'],1)

    def test_late_completed_work_counts_complete_but_not_on_time(self):
        self.task.due_at=self.now-timedelta(days=1);self.task.save()
        self.review(self.submit(),'complete',score=7)
        data=metrics_for(self.student)
        self.assertEqual(data['completed_count'],1)
        self.assertEqual(data['on_time_completed_count'],0)

    def test_grade_of_older_attempt_cannot_overwrite_newer_assessment(self):
        older=self.submit('older')
        newer=self.submit('newer')
        self.review(newer,'incomplete',score=4)
        self.review(older,'complete',score=9)
        newer.progress.refresh_from_db()
        self.assertEqual((newer.progress.status,newer.progress.score),('incomplete',40))
        self.assertEqual(metrics_for(self.student)['completed_count'],0)

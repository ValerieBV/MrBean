"""Verify that a source-branch database upgrades without losing learning history."""
from datetime import timedelta
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class SourceDatabaseUpgradeTests(TransactionTestCase):
    migrate_from = [('accounts','0003_customuser_student_code'),
        ('assignments','0003_lesson_reference_transcript'),
        ('courses','0002_alter_studentexemptionquota_options_and_more'),
        ('dashboard','0002_learningtask_assignment'), ('ai_core','0003_alter_gradingjob_status'),
        ('submissions','0001_initial')]

    def setUp(self):
        executor=MigrationExecutor(connection)
        self.migrate_to=executor.loader.graph.leaf_nodes()
        executor.migrate(self.migrate_from)
        self.old_apps=executor.loader.project_state(self.migrate_from).apps

    def tearDown(self):
        MigrationExecutor(connection).migrate(self.migrate_to)
        super().tearDown()

    def seed_source_history(self,duplicate=False):
        get=self.old_apps.get_model
        User=get('accounts','CustomUser');Course=get('courses','Course');Room=get('courses','ClassRoom')
        Enrollment=get('courses','Enrollment');Quota=get('courses','StudentExemptionQuota')
        Lesson=get('assignments','Lesson');Assignment=get('assignments','ClassAssignment')
        Task=get('dashboard','LearningTask');Job=get('ai_core','GradingJob');Progress=get('submissions','LessonProgress')
        teacher=User.objects.create(username='legacy_teacher',role='teacher')
        User.objects.create(username='legacy_root',role='student',is_superuser=True,is_staff=False)
        student=User.objects.create(username='legacy_student',role='student',student_code='T2026Legacy')
        course=Course.objects.create(code='OLD',name='Source course')
        room=Room.objects.create(class_code='OLD-1',name='Source class',course=course,teacher=teacher)
        enrollment=Enrollment.objects.create(classroom=room,student=student,status='active')
        Quota.objects.create(enrollment=enrollment,max_quota=8,used_quota=2)
        if duplicate:
            other=Room.objects.create(class_code='OLD-2',name='Other source class',course=course,teacher=teacher)
            Enrollment.objects.create(classroom=other,student=student,status='active')
        now=timezone.now()
        lesson=Lesson.objects.create(skill='speaking',program='CHUNG',order=1,title='Old speaking',reference_transcript='Old exact sample.')
        assignment=Assignment.objects.create(lesson=lesson,classroom=room,assigned_at=now-timedelta(days=2),due_at=now+timedelta(days=1),rubric={'skill':'speaking','reference_transcript':'Old exact sample.'})
        task=Task.objects.create(assignment=assignment,assignment_key='old-task',title=lesson.title,teacher=teacher,learner=student,assigned_at=assignment.assigned_at,due_at=assignment.due_at)
        progress=Progress.objects.create(student=student,lesson=lesson,status='completed',score=82)
        job=Job.objects.create(task=task,progress=progress,submission_key='old-job',kind='speaking',status='graded',
            final_score=8.2,transcript='Old transcript.',teacher_feedback='Old confirmed feedback',rubric_snapshot=assignment.rubric)
        return student.pk,task.pk,job.pk,progress.pk

    def assert_history_after_upgrade(self,ids):
        from accounts.models import CustomUser
        from courses.models import Enrollment
        from dashboard.models import LearningTask
        from ai_core.models import GradingJob
        from submissions.models import LessonProgress
        student_id,task_id,job_id,progress_id=ids
        self.assertEqual(CustomUser.objects.get(pk=student_id).student_code,'T2026Legacy')
        root=CustomUser.objects.get(username='legacy_root')
        self.assertEqual(root.role,'admin');self.assertTrue(root.is_staff)
        self.assertEqual(Enrollment.objects.get(student_id=student_id,status='active').exemption_quota.used_quota,2)
        self.assertIsNone(LearningTask.objects.get(pk=task_id).exemption_id)
        job=GradingJob.objects.get(pk=job_id)
        self.assertEqual((job.final_score,job.transcript,job.teacher_feedback),(8.2,'Old transcript.','Old confirmed feedback'))
        self.assertEqual(job.rubric_snapshot['reference_transcript'],'Old exact sample.')
        self.assertEqual(job.completion_status, 'pending')
        progress = LessonProgress.objects.get(pk=progress_id)
        self.assertEqual(progress.score,82)
        self.assertEqual(progress.status, 'assessed')
        self.assertIsNone(progress.completed_at)

    def test_upgrade_retains_ids_scores_rubrics_and_quota(self):
        ids=self.seed_source_history()
        MigrationExecutor(connection).migrate(self.migrate_to)
        self.assert_history_after_upgrade(ids)

    def test_listening_history_preserves_questions_and_derives_completion_from_work(self):
        student_id, source_task_id, _, _ = self.seed_source_history()
        get = self.old_apps.get_model
        Lesson = get('assignments', 'Lesson'); Question = get('assignments', 'ListeningQuestion')
        Assignment = get('assignments', 'ClassAssignment'); Task = get('dashboard', 'LearningTask')
        Job = get('ai_core', 'GradingJob'); Progress = get('submissions', 'LessonProgress')
        source = Task.objects.get(pk=source_task_id)
        records = []
        for index, (choices, expected, score) in enumerate([
                (['B', 'B'], 'complete', 0), (['A', ''], 'incomplete', 10),
                (['AB', 'A'], 'pending', 10)], 1):
            lesson = Lesson.objects.create(skill='listening', program='B1', order=index,
                title='Legacy listening ' + str(index), audio_file='lessons/audio/legacy.mp3')
            questions = [Question.objects.create(lesson=lesson, order=n, correct_option='A',
                option_a='A', option_b='B', option_c='C', option_d='D') for n in (1, 2)]
            rubric = {'skill': 'listening', 'questions': [
                {'id': q.pk, 'correct_option': 'A'} for q in questions]}
            assignment = Assignment.objects.create(lesson=lesson, classroom_id=source.assignment.classroom_id,
                assigned_at=source.assigned_at, due_at=source.due_at, rubric=rubric)
            task = Task.objects.create(assignment=assignment, assignment_key='listen-' + str(index),
                title=lesson.title, teacher_id=source.teacher_id, learner_id=student_id,
                assigned_at=source.assigned_at, due_at=source.due_at)
            progress = Progress.objects.create(student_id=student_id, lesson=lesson,
                status='completed', score=score * 10)
            job = Job.objects.create(task=task, progress=progress, submission_key='listen-' + str(index),
                kind='listening', status='graded', final_score=score, rubric_snapshot=rubric,
                teacher_feedback='Unchanged legacy feedback',
                answers={str(q.pk): choice for q, choice in zip(questions, choices)}, finished_at=timezone.now())
            records.append((lesson.pk, [q.pk for q in questions], job.pk, progress.pk, expected, score, rubric))
        MigrationExecutor(connection).migrate(self.migrate_to)
        from assignments.models import ListeningExercise, ListeningQuestion
        from ai_core.models import GradingJob
        from submissions.models import LessonProgress
        for lesson_id, question_ids, job_id, progress_id, expected, score, rubric in records:
            exercise = ListeningExercise.objects.get(lesson_id=lesson_id)
            self.assertEqual((exercise.kind, exercise.question_count), ('legacy', 2))
            self.assertEqual(exercise.audio_file.name, 'lessons/audio/legacy.mp3')
            self.assertEqual(list(ListeningQuestion.objects.filter(exercise=exercise).values_list('pk', flat=True)), question_ids)
            job = GradingJob.objects.get(pk=job_id)
            self.assertEqual((job.completion_status, job.final_score), (expected, score))
            self.assertEqual(job.rubric_snapshot, rubric)
            self.assertEqual(job.teacher_feedback, 'Unchanged legacy feedback')
            progress = LessonProgress.objects.get(pk=progress_id)
            self.assertEqual(progress.status, {'complete':'completed', 'incomplete':'incomplete', 'pending':'assessed'}[expected])
            self.assertEqual(progress.score, score * 10)

    def test_duplicate_active_enrollment_requires_review_without_deleting_data(self):
        ids=self.seed_source_history(duplicate=True)
        with self.assertRaisesMessage(RuntimeError,'Student IDs'):
            MigrationExecutor(connection).migrate(self.migrate_to)
        Enrollment=self.old_apps.get_model('courses','Enrollment')
        self.assertEqual(Enrollment.objects.filter(student_id=ids[0],status='active').count(),2)
        Enrollment.objects.filter(student_id=ids[0],classroom__class_code='OLD-2').update(status='completed')
        MigrationExecutor(connection).migrate(self.migrate_to)
        self.assert_history_after_upgrade(ids)

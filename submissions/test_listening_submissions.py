import json
import uuid
from datetime import timedelta
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from assignments.forms import ListeningExerciseForm
from assignments.models import Lesson
from assignments.services import assign_to_class, save_listening_exercise
from assignments.test_listening_solutions import bundle_for
from dashboard.services import annotated_tasks, metrics_for
from dashboard.testutils import IntegratedFixture
from support.ai import context_for
from support.models import Conversation
from ai_core.services import enqueue_submission
from .listening_review import focused_question
from .models import LessonProgress


class IndependentListeningSubmissionTests(IntegratedFixture):
    def setUp(self):
        super().setUp()
        lesson = Lesson.objects.create(skill='listening', program='B1', order=83,
            title='Four independent exercises', created_by=self.teacher)
        self.exercises = []
        for order, kind in enumerate(('part1', 'part2', 'part3', 'part4'), 1):
            files = {'audio_file': SimpleUploadedFile('audio.mp3', b'ID3-test')}
            if kind == 'part1':
                files['document_file'] = SimpleUploadedFile('paper.pdf', b'%PDF-1.4\n%%EOF')
            form = ListeningExerciseForm({'kind':kind, 'order':order,
                'solution_data':json.dumps(bundle_for(kind))}, files, lesson=lesson)
            self.assertTrue(form.is_valid(), form.errors)
            self.exercises.append(save_listening_exercise(actor=self.teacher, form=form))
        assignment = assign_to_class(actor=self.teacher, lesson=lesson, classroom=self.classroom,
            assigned_at=self.now-timedelta(days=1), due_at=self.now+timedelta(days=1), requires_previous=False)
        self.quiz = assignment.tasks.get(learner=self.student)
        self.client.force_login(self.student)
        self.review_url = reverse('submissions:task_listening_review', args=[self.quiz.pk])

    def answers(self, exercise, chosen='B'):
        return {str(q.pk): {'chosen':chosen, 'short_answer':'A response'} for q in exercise.questions.all()}

    def submit(self, index, **kwargs):
        exercise = self.exercises[index]
        return enqueue_submission(task=self.quiz, submission_key=uuid.uuid4().hex,
            exercise_id=exercise.pk, answers=self.answers(exercise), **kwargs)[0]

    def api_submit(self, exercise, *, key=None, answers=None):
        data = {'task_id':self.quiz.pk, 'submission_key':key or uuid.uuid4().hex,
            'reference_version':self.quiz.assignment.reference_version,
            'answers':self.answers(exercise) if answers is None else answers}
        if exercise:
            data['exercise_id'] = exercise.pk
        return self.client.post(reverse('ai_core:submit'), data, content_type='application/json')

    def test_dashboard_separates_partial_listening_from_fully_submitted_work(self):
        filters = {'q': self.quiz.title}
        before = metrics_for(self.student, filters=filters)
        self.assertEqual((before['tasks'][0]['submitted_exercise_count'], before['tasks'][0]['exercise_count']), (0, 4))
        self.submit(1)
        partial = metrics_for(self.student, filters=filters)
        self.assertEqual((partial['submitted_count'], partial['full_count'], partial['completed_count']), (1, 0, 0))
        row = partial['next_tasks'][0]
        self.assertEqual((row['stage'], row['submitted_exercise_count'], row['exercise_count']), ('partial', 1, 4))
        self.assertEqual(self.client.get(row['action_url']).status_code, 200)
        for i in (3, 0, 2):
            self.submit(i)
        done = metrics_for(self.student, filters=filters)
        self.assertEqual((done['full_count'], done['completed_count'], done['action_count']), (1, 1, 0))
        self.assertEqual(done['tasks'][0]['stage'], 'complete')

    def test_any_exercise_can_be_submitted_first_and_only_its_answers_are_published(self):
        job = self.submit(1)
        self.assertEqual(job.result['total'], 25)
        self.assertEqual(job.result['exercise_result']['correct_count'], 25)
        self.assertEqual(job.completion_status, 'incomplete')
        self.assertEqual([e['id'] for e in job.rubric_snapshot['exercises']], [self.exercises[1].pk])
        self.assertEqual(set(job.answers), set(self.answers(self.exercises[1])))
        self.assertEqual(self.client.get(self.review_url, {'exercise':self.exercises[0].pk}).status_code, 404)
        page = self.client.get(self.review_url)
        self.assertContains(page, 'PRIVATE_EXPLANATION_7')
        self.assertNotContains(page, 'PRIVATE_EXPLANATION_1')
        self.assertNotContains(page, 'PRIVATE_PASSAGE_32')
        self.assertEqual(page['Cache-Control'], 'private, no-store')
        for url in (reverse('submissions:result', args=[job.pk]), reverse('ai_core:detail', args=[job.pk])):
            response = self.client.get(url)
            self.assertNotContains(response, 'PRIVATE_PASSAGE_32')
            self.assertNotContains(response, 'PRIVATE_EXPLANATION_71')
        missing_id = self.exercises[2].questions.first().pk
        self.assertEqual(self.client.get(reverse('support:start_question', args=[job.pk, missing_id])).status_code, 404)
        with self.assertRaises(ValueError):
            focused_question(job, missing_id)
        thread = Conversation.objects.create(student=self.student, job=job, kind='knowledge', subject='Question')
        context = context_for(thread)
        self.assertEqual({int(q['id']) for q in context['questions']}, set(self.exercises[1].questions.values_list('pk', flat=True)))

    def test_lesson_completes_only_when_all_exercises_have_required_responses(self):
        for index in (2, 0, 3):
            job = self.submit(index)
            self.assertEqual(job.completion_status, 'incomplete')
            self.assertEqual(annotated_tasks(self.student).get(pk=self.quiz.pk).confirmed_completion, 'incomplete')
        job = self.submit(1)
        self.assertEqual(job.completion_status, 'complete')
        self.assertEqual(job.result['total'], 100)
        self.assertEqual(job.result['missing_count'], 0)
        progress = LessonProgress.objects.get(student=self.student, lesson=self.quiz.assignment.lesson)
        self.assertEqual(progress.status, 'completed')
        self.assertEqual(next(row for row in metrics_for(self.student)['tasks'] if row['id'] == self.quiz.pk)['completion_status'], 'complete')

    def test_retry_updates_only_selected_exercise_and_keeps_other_results(self):
        first = self.submit(0)
        self.submit(1)
        job, _ = enqueue_submission(task=self.quiz, submission_key='retry-one',
            exercise_id=self.exercises[1].pk, answers=self.answers(self.exercises[1], chosen='A'))
        for key, value in first.answers.items():
            self.assertEqual(job.answers[key], value)
        self.assertEqual(job.result['exercise_result']['correct_count'], 0)
        self.assertEqual(job.result['correct_count'], 6)
        first.refresh_from_db()
        self.assertEqual(len(first.answers), 6)

    def test_draft_of_other_exercises_survives_submission(self):
        answers = {**self.answers(self.exercises[0]), **self.answers(self.exercises[2])}
        response = self.client.post(reverse('submissions:autosave', args=[self.quiz.pk]),
            {'answers':answers, 'reference_version':self.quiz.assignment.reference_version}, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.submit(0)
        self.quiz.refresh_from_db()
        self.assertTrue(self.quiz.draft_valid)
        for key in self.answers(self.exercises[2]):
            self.assertEqual(self.quiz.draft['answers'][key], answers[key])
        self.assertTrue(set(self.answers(self.exercises[0])).isdisjoint(self.quiz.draft['answers']))
        page = self.client.get(reverse('submissions:do_task', args=[self.quiz.pk]))
        self.assertContains(page, 'data-submit-exercise=', count=4)
        self.assertContains(page, f'?exercise={self.exercises[0].pk}', count=1)
        self.assertNotContains(page, f'?exercise={self.exercises[2].pk}')

    def test_api_rejects_unscoped_or_foreign_answers_and_is_idempotent(self):
        self.assertEqual(self.api_submit(None, answers={}).status_code, 400)
        self.assertEqual(self.api_submit(self.exercises[0], answers=self.answers(self.exercises[1])).status_code, 400)
        invalid = self.client.post(reverse('ai_core:submit'), {'task_id':self.quiz.pk,
            'submission_key':'invalid-exercise', 'exercise_id':999999, 'answers':{}}, content_type='application/json')
        self.assertEqual(invalid.status_code, 400)
        first = self.api_submit(self.exercises[0], key='same-exercise')
        self.assertEqual(first.status_code, 201)
        second = self.api_submit(self.exercises[0], key='same-exercise')
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()['id'], second.json()['id'])
        self.assertEqual(self.api_submit(self.exercises[1], key='same-exercise').status_code, 400)
        self.assertEqual(self.quiz.jobs.count(), 1)

    def test_before_deadline_no_submission_means_no_solutions(self):
        self.assertEqual(self.client.get(self.review_url).status_code, 404)
        self.assertNotContains(self.client.get(reverse('submissions:do_task', args=[self.quiz.pk])), 'Đáp án và giải thích')

    def test_deadline_opens_all_solutions_without_creating_a_submission_or_completion(self):
        type(self.quiz).objects.filter(pk=self.quiz.pk).update(due_at=self.now-timedelta(seconds=1))
        page = self.client.get(reverse('submissions:do_task', args=[self.quiz.pk]))
        self.assertContains(page, 'Đáp án và giải thích')
        skill_page = self.client.get(reverse('submissions:student_skill', args=['listening']))
        self.assertContains(skill_page, self.review_url)
        for exercise in self.exercises:
            response = self.client.get(self.review_url, {'exercise':exercise.pk})
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'PRIVATE_EXPLANATION_')
            self.assertNotContains(response, 'Hỏi AI')
        self.assertFalse(self.quiz.jobs.exists())
        self.assertIsNone(annotated_tasks(self.student).get(pk=self.quiz.pk).confirmed_completion)

    def test_deadline_with_one_submission_releases_other_exercises_without_tutor_leak(self):
        self.submit(0)
        type(self.quiz).objects.filter(pk=self.quiz.pk).update(due_at=self.now-timedelta(seconds=1))
        response = self.client.get(self.review_url, {'exercise':self.exercises[2].pk})
        self.assertContains(response, 'PRIVATE_PASSAGE_32')
        self.assertNotContains(response, 'Hỏi AI')

    def test_other_learner_and_future_assignment_cannot_use_review(self):
        self.submit(0)
        self.client.force_login(self.other_student)
        self.assertEqual(self.client.get(self.review_url).status_code, 404)
        self.client.force_login(self.student)
        type(self.quiz).objects.filter(pk=self.quiz.pk).update(assigned_at=self.now+timedelta(days=1))
        self.assertEqual(self.client.get(self.review_url).status_code, 404)

    def test_legacy_whole_lesson_attempt_keeps_previously_published_exercises(self):
        from ai_core.models import GradingJob
        answers = {key:value for exercise in self.exercises for key,value in self.answers(exercise).items()}
        GradingJob.objects.create(task=self.quiz, kind='listening', status='graded',
            submission_key='legacy-whole', rubric_snapshot=self.quiz.assignment.rubric, answers=answers)
        job = self.submit(1)
        self.assertEqual(job.result['submitted_exercise_count'], 4)
        self.assertEqual(job.completion_status, 'complete')

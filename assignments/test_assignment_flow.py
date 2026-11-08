from datetime import timedelta
from django.core.exceptions import ValidationError, PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from dashboard.testutils import IntegratedFixture
from courses.models import Enrollment
from .forms import AssignmentForm, ListeningExerciseForm
from .models import Lesson, ClassAssignment, ListeningQuestion, VocabWord
from .preview import build_assignment_preview
from .services import assign_to_class, save_listening_exercise, lesson_rubric


class AssignmentFlowTests(IntegratedFixture):
    def setUp(self):
        super().setUp()
        self.lesson = Lesson.objects.create(skill='listening', program='B1', order=21,
            title='Buổi nghe cần kiểm tra', created_by=self.teacher)

    def body(self, **updates):
        data = {'lesson': self.lesson.pk, 'classroom': self.classroom.pk,
            'assigned_at': timezone.localtime(self.now).strftime('%Y-%m-%dT%H:%M'),
            'due_at': timezone.localtime(self.now+timedelta(days=1)).strftime('%Y-%m-%dT%H:%M'),
            'allow_late_submission': 'on', 'requires_previous': 'on'}
        return {**data, **updates}

    def exercise(self, kind='part2', count=25):
        form = ListeningExerciseForm({'order':1, 'kind':kind, 'question_count':count,
            'answer_key':' '.join(['C']*count)},
            {'audio_file':SimpleUploadedFile('listening.mp3', b'ID3-test')}, lesson=self.lesson)
        self.assertTrue(form.is_valid(), form.errors)
        return save_listening_exercise(actor=self.teacher, form=form)

    def test_empty_lesson_reports_missing_content_instead_of_generic_A_to_D_error(self):
        with self.assertRaisesMessage(ValidationError, 'Buổi nghe chưa có bài tập hoặc câu hỏi'):
            lesson_rubric(self.lesson)
        self.client.force_login(self.teacher)
        response = self.client.post(reverse('assignments:assign'), self.body())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Buổi nghe chưa có bài tập hoặc câu hỏi')
        self.assertContains(response, 'Quản lý bài tập / bổ sung nội dung')
        self.assertFalse(ClassAssignment.objects.filter(lesson=self.lesson).exists())

    def test_three_choice_exercise_assigns_without_vocabulary_repetitions(self):
        self.exercise()
        form = AssignmentForm(self.body(), user=self.teacher)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['repetitions'], 1)
        self.client.force_login(self.teacher)
        response = self.client.post(reverse('assignments:assign'), self.body())
        self.assertEqual(response.status_code, 302)
        saved = ClassAssignment.objects.get(lesson=self.lesson)
        self.assertEqual(saved.tasks.count(), 1)
        self.assertEqual(len(saved.rubric['questions']), 25)
        self.assertTrue(all(q['choice_letters']=='ABC' and not q['option_d'] for q in saved.rubric['questions']))

    def test_invalid_answer_identifies_exact_question_and_allowed_letters(self):
        exercise = self.exercise()
        exercise.questions.filter(order=7).update(correct_option='D')
        with self.assertRaisesMessage(ValidationError, 'Bài 1, câu 7') as error:
            lesson_rubric(self.lesson)
        self.assertIn('A / B / C;', str(error.exception))
        preview = build_assignment_preview(self.lesson, self.classroom)
        self.assertFalse(preview['ready'])
        self.assertTrue(any('câu 7' in message for message in preview['problems']))

    def test_missing_option_and_uploaded_audio_are_reported_before_assignment(self):
        exercise = self.exercise()
        exercise.questions.filter(order=3).update(option_a='')
        exercise.audio_file.storage.delete(exercise.audio_file.name)
        preview = build_assignment_preview(self.lesson, self.classroom)
        self.assertFalse(preview['ready'])
        self.assertTrue(any('file nghe không còn' in message for message in preview['problems']))
        self.assertTrue(any('câu 3: thiếu lựa chọn A' in message for message in preview['problems']))

    def test_preview_does_not_publish_keys_and_rejects_other_class_or_student(self):
        self.exercise()
        url = reverse('assignments:assign_preview')
        self.client.force_login(self.teacher)
        response = self.client.get(url, {'lesson': self.lesson.pk, 'classroom': self.classroom.pk})
        data = response.json()
        self.assertTrue(data['ready'])
        self.assertEqual(data['skill'], 'listening')
        self.assertIn('25 câu', data['html'])
        self.assertNotIn('correct_option', response.content.decode())
        self.assertNotIn('correct_answer', response.content.decode())
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        self.assertEqual(self.client.get(url, {'lesson': self.lesson.pk, 'classroom': self.other_classroom.pk}).status_code, 404)
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(url, {'lesson': self.lesson.pk}).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(url, {'lesson': self.lesson.pk}).status_code, 401)

    def test_duplicate_assignment_keeps_roster_and_snapshot_and_shows_existing_link(self):
        exercise = self.exercise()
        saved = assign_to_class(actor=self.teacher, lesson=self.lesson, classroom=self.classroom,
            assigned_at=self.now, due_at=self.now+timedelta(days=1))
        snapshot = saved.rubric.copy()
        exercise.questions.update(correct_option='')
        with self.assertRaisesMessage(ValidationError, 'đã được giao cho lớp'):
            assign_to_class(actor=self.teacher, lesson=self.lesson, classroom=self.classroom,
                assigned_at=self.now, due_at=self.now+timedelta(days=2))
        self.client.force_login(self.teacher)
        response = self.client.post(reverse('assignments:assign'), self.body())
        self.assertContains(response, reverse('assignments:assigned_detail', args=[saved.pk]))
        saved.refresh_from_db()
        self.assertEqual(saved.rubric, snapshot)
        self.assertEqual(saved.tasks.count(), 1)
        self.assertEqual(ClassAssignment.objects.filter(lesson=self.lesson).count(), 1)

    def test_dates_vocabulary_and_teacher_requirements_are_field_errors(self):
        before = timezone.localtime(self.now-timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
        form = AssignmentForm(self.body(due_at=before), user=self.teacher)
        self.assertFalse(form.is_valid());self.assertIn('due_at', form.errors)
        vocab = Lesson.objects.create(skill='vocabulary', program='B1', order=21, title='Từ vựng mới')
        VocabWord.objects.create(lesson=vocab, word='Hello')
        form = AssignmentForm(self.body(lesson=vocab.pk), user=self.teacher)
        self.assertFalse(form.is_valid());self.assertIn('repetitions', form.errors)
        self.classroom.teacher = None;self.classroom.save(update_fields=['teacher'])
        form = AssignmentForm(self.body(), user=self.manager)
        self.assertFalse(form.is_valid());self.assertIn('classroom', form.errors)

    def test_revalidates_current_class_teacher_instead_of_stale_form_object(self):
        self.exercise()
        type(self.classroom).objects.filter(pk=self.classroom.pk).update(teacher=self.other_teacher)
        with self.assertRaises(PermissionDenied):
            assign_to_class(actor=self.teacher, lesson=self.lesson, classroom=self.classroom,
                assigned_at=self.now, due_at=self.now+timedelta(days=1))
        self.assertFalse(ClassAssignment.objects.filter(lesson=self.lesson).exists())

    def test_inactive_learners_do_not_receive_new_assignments_or_affect_preview_count(self):
        self.exercise()
        self.student.is_active=False;self.student.save(update_fields=['is_active'])
        self.assertTrue(Enrollment.objects.filter(classroom=self.classroom, student=self.student, status='active').exists())
        preview = build_assignment_preview(self.lesson, self.classroom)
        self.assertEqual(preview['classroom']['student_count'], 0)
        self.assertTrue(preview['ready'])
        self.assertTrue(preview['warnings'])
        saved=assign_to_class(actor=self.teacher, lesson=self.lesson, classroom=self.classroom,
            assigned_at=self.now, due_at=self.now+timedelta(days=1))
        self.assertEqual(saved.tasks.count(), 0)

import io
from datetime import timedelta
from django.core.exceptions import ValidationError, PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from django.urls import reverse
from assignments.listening import parse_answer_key
from assignments.models import Lesson, ListeningExercise
from assignments.forms import ListeningExerciseForm
from assignments.services import save_listening_exercise, assign_to_class
from dashboard.testutils import IntegratedFixture
from ai_core.services import enqueue_submission


class AnswerKeyTests(SimpleTestCase):
    def test_paste_numbered_letters_and_excel_column(self):
        for value in ['1.A 2.C 3.B 4.D 5.A 6.C', '1,A\n2,C\n3,B\n4,D\n5,A\n6,C', 'A\nC\nB\nD\nA\nC', 'ACBDAC']:
            self.assertEqual([x['answer'] for x in parse_answer_key(value, 6, 'ABCD')], list('ACBDAC'))

    def test_csv_can_import_question_and_option_text(self):
        rows = parse_answer_key('number,answer,question_text,A,B,C\n1,B,"Where, exactly?",Here,There,Everywhere', 1, 'ABC')
        self.assertEqual(rows[0]['question_text'], 'Where, exactly?')
        self.assertEqual(rows[0]['option_b'], 'There')

    def test_missing_duplicate_unknown_and_part2_D_are_rejected(self):
        for value, count, choices in [('1.A 1.B', 2, 'ABCD'), ('A B', 3, 'ABCD'),
                ('A D', 2, 'ABC'), ('1.A 3.B', 2, 'ABCD'), ('A X', 2, 'ABCD'),
                ('number,answer\n1,AB', 1, 'ABCD'), ('number,answer\n1,', 1, 'ABCD')]:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                parse_answer_key(value, count, choices)


class ListeningExerciseTests(IntegratedFixture):
    def setUp(self):
        super().setUp()
        self.lesson = Lesson.objects.create(skill='listening', program='B1', order=20,
            title='Buổi nghe bốn dạng', created_by=self.teacher)

    def form(self, kind='part1', order=1, count=None, key=None, document=True, instance=None):
        count = count or {'part1':6, 'part2':25, 'part3':39, 'part4':30}[kind]
        data = {'kind':kind, 'order':order, 'title':'Bài nghe thử', 'question_count':count,
            'answer_key':key or ' '.join('A' for _ in range(count))}
        files = {'audio_file':SimpleUploadedFile('audio.mp3', b'ID3-test-audio', content_type='audio/mpeg')}
        if document:
            files['document_file'] = SimpleUploadedFile('de-bai.pdf', b'%PDF-1.4\n%%EOF', content_type='application/pdf')
        return ListeningExerciseForm(data, files, lesson=self.lesson, instance=instance)

    def save(self, **kwargs):
        form = self.form(**kwargs)
        self.assertTrue(form.is_valid(), form.errors.as_json())
        return save_listening_exercise(actor=self.teacher, form=form)

    def assign(self):
        return assign_to_class(actor=self.teacher, lesson=self.lesson, classroom=self.classroom,
            assigned_at=self.now-timedelta(minutes=1), due_at=self.now+timedelta(days=1), requires_previous=False)

    def test_new_lesson_has_no_default_exercises_and_empty_lesson_cannot_be_assigned(self):
        self.assertEqual(self.lesson.listening_exercises.count(), 0)
        with self.assertRaises(ValidationError): self.assign()
        self.client.force_login(self.teacher)
        page = self.client.get(reverse('assignments:lesson_detail', args=[self.lesson.pk]))
        self.assertContains(page, 'Chưa thêm bài nghe')
        self.assertContains(page, 'Thêm bài nghe')

    def test_authoring_is_visible_from_bank_and_each_type_card_preselects_its_form(self):
        self.client.force_login(self.teacher)
        bank = self.client.get(reverse('assignments:skill_lessons', args=['listening']))
        self.assertContains(bank, 'Quản lý bài tập')
        self.assertContains(bank, reverse('assignments:lesson_detail', args=[self.lesson.pk]) + '#them-bai-nghe')
        detail = self.client.get(reverse('assignments:lesson_detail', args=[self.lesson.pk]))
        self.assertContains(detail, 'data-add-listening-kind=', count=4)
        create_url = reverse('assignments:listening_exercise_create', args=[self.lesson.pk])
        for kind, count in [('part1',6), ('part2',25), ('part3',39), ('part4',30)]:
            with self.subTest(kind=kind):
                self.assertContains(detail, create_url + '?kind=' + kind)
                form_page = self.client.get(create_url, {'kind':kind})
                self.assertEqual(form_page.context['form']['kind'].value(), kind)
                self.assertEqual(form_page.context['form']['question_count'].value(), count)
        self.assertEqual(self.lesson.listening_exercises.count(), 0)
        fallback = self.client.get(create_url, {'kind':'legacy'})
        self.assertEqual(fallback.context['form']['kind'].value(), 'part1')

    def test_locked_lesson_keeps_type_cards_and_explains_how_to_add_with_a_copy(self):
        self.save()
        self.assign()
        self.client.force_login(self.teacher)
        page = self.client.get(reverse('assignments:lesson_detail', args=[self.lesson.pk]))
        self.assertContains(page, 'data-listening-kind=', count=4)
        self.assertNotContains(page, 'data-add-listening-kind=')
        self.assertContains(page, 'Tạo bản sao để thêm bài tập')
        self.assertContains(page, 'Buổi đã giao hoặc có lịch sử bài làm')
        self.assertNotContains(page, 'Sửa tài liệu / đáp án')

    def test_other_author_has_a_read_only_explanation_and_students_cannot_author(self):
        self.client.force_login(self.other_teacher)
        page = self.client.get(reverse('assignments:lesson_detail', args=[self.lesson.pk]))
        self.assertContains(page, 'Bạn đang xem buổi do người khác biên soạn')
        self.assertNotContains(page, 'data-add-listening-kind=')
        self.assertNotContains(page, 'Buổi đã giao hoặc có lịch sử bài làm')
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse('assignments:lesson_detail', args=[self.lesson.pk])).status_code, 403)

    def test_full_lesson_keeps_four_type_descriptions_and_blocks_the_fifth_form(self):
        for order in range(1,5):
            self.save(kind='part4', order=order)
        self.client.force_login(self.teacher)
        page = self.client.get(reverse('assignments:lesson_detail', args=[self.lesson.pk]))
        self.assertContains(page, 'data-listening-kind=', count=4)
        self.assertNotContains(page, 'data-add-listening-kind=')
        self.assertContains(page, 'Đã đủ 4 bài nghe trong buổi')
        self.assertRedirects(self.client.get(reverse('assignments:listening_exercise_create', args=[self.lesson.pk])),
            reverse('assignments:lesson_detail', args=[self.lesson.pk]))
        self.assertEqual(self.lesson.listening_exercises.count(), 4)

    def test_four_kinds_have_exact_counts_and_only_three_options_in_part2(self):
        for index, kind in enumerate(['part1','part2','part3','part4'], 1):
            exercise = self.save(kind=kind, order=index)
            self.assertEqual(exercise.questions.count(), {'part1':6,'part2':25,'part3':39,'part4':30}[kind])
            self.assertTrue(exercise.questions.exclude(option_d='').exists() if kind!='part2'
                            else not exercise.questions.exclude(option_d='').exists())
        assignment = self.assign()
        self.assertEqual(len(assignment.rubric['exercises']), 4)
        self.assertEqual(len(assignment.rubric['questions']), 100)
        self.assertTrue(all(q['requires_short_answer'] for q in assignment.rubric['questions']))

    def test_each_lesson_cannot_have_a_fifth_exercise(self):
        for order in range(1,5):self.save(kind='part4', order=order)
        form = self.form(kind='part4', order=5)
        self.assertFalse(form.is_valid())
        with self.assertRaises(ValidationError):
            # The service also checks the cap inside a locked lesson.
            form = self.form(kind='part4', order=1)
            form.is_valid()
            save_listening_exercise(actor=self.teacher, form=form)
        self.assertEqual(self.lesson.listening_exercises.count(), 4)

    def test_fixed_question_counts_pdf_and_audio_are_checked(self):
        for kind, count in [('part1',5), ('part2',24), ('part3',38), ('part4',29), ('part4',31)]:
            form = self.form(kind=kind, count=count)
            self.assertFalse(form.is_valid(), kind)
        form = self.form(document=False)
        self.assertFalse(form.is_valid());self.assertIn('document_file', form.errors)
        form = self.form()
        form.files['document_file'] = SimpleUploadedFile('fake.pdf', b'<html>not a PDF</html>')
        self.assertFalse(form.is_valid());self.assertIn('document_file', form.errors)
        form = self.form()
        form.files['audio_file'] = SimpleUploadedFile('bad.exe', b'bad')
        self.assertFalse(form.is_valid())

    def test_bulk_csv_upload_creates_all_answers_without_individual_entry(self):
        form = self.form(kind='part2', document=False)
        form.data['answer_key'] = ''
        form.files['answer_key_file'] = SimpleUploadedFile('dap-an.csv',
            ('number,answer\n'+'\n'.join(f'{i},B' for i in range(1,26))).encode('utf-8'))
        self.assertTrue(form.is_valid(),form.errors)
        exercise = save_listening_exercise(actor=self.teacher, form=form)
        self.assertEqual(exercise.questions.filter(correct_option='B').count(),25)
        self.assertFalse(exercise.questions.exclude(option_d='').exists())

    def test_snapshot_and_pdf_access_are_scoped_and_inline(self):
        exercise = self.save()
        assignment = self.assign()
        task = assignment.tasks.get(learner=self.student)
        old_key = assignment.rubric['questions'][0]['correct_option']
        exercise.questions.update(correct_option='D')
        self.assertEqual(assignment.rubric['questions'][0]['correct_option'], old_key)
        url = reverse('submissions:listening_material', args=[task.pk, exercise.pk, 'document'])
        for user, status in [(self.other_student,404),(self.other_teacher,404),(self.student,200)]:
            self.client.force_login(user)
            response = self.client.get(url)
            self.assertEqual(response.status_code, status)
            if status==200:
                self.assertEqual(response['Content-Type'],'application/pdf')
                self.assertEqual(response['X-Frame-Options'],'SAMEORIGIN')
                self.assertNotIn('attachment',response.get('Content-Disposition',''))
                response.close()
        self.client.force_login(self.student)
        page = self.client.get(reverse('submissions:do_task',args=[task.pk]))
        self.assertContains(page,'class="listening-pdf"')
        self.assertNotContains(page,'correct_option')
        self.assertContains(page,'name="s_',count=6)
        self.assertContains(page,'type="radio"',count=24)
        job,_=enqueue_submission(task=task,submission_key='snapshot-pdf',answers={})
        result_url=reverse('ai_core:listening_material',args=[job.pk,exercise.pk,'document'])
        response=self.client.get(result_url);self.assertEqual(response.status_code,200);response.close()
        self.client.force_login(self.other_student);self.assertEqual(self.client.get(result_url).status_code,404)

    def test_assigned_exercises_are_locked_and_clones_keep_question_groups(self):
        exercise=self.save()
        self.assign()
        self.client.force_login(self.teacher)
        response=self.client.post(reverse('assignments:lesson_clone',args=[self.lesson.pk]))
        self.assertEqual(response.status_code,302)
        clone=Lesson.objects.get(title=self.lesson.title+' (bản sao)')
        self.assertEqual(clone.listening_exercises.count(),1)
        copied=clone.listening_exercises.get()
        self.assertNotEqual(copied.pk,exercise.pk)
        self.assertEqual(copied.questions.count(),6)
        self.assertEqual(clone.questions.filter(exercise=copied).count(),6)
        form=self.form(instance=exercise)
        self.assertTrue(form.is_valid(),form.errors)
        with self.assertRaises(ValidationError):save_listening_exercise(actor=self.teacher,form=form)

    def test_other_teacher_cannot_mutate_lesson(self):
        form=self.form();self.assertTrue(form.is_valid(),form.errors)
        with self.assertRaises(PermissionDenied):save_listening_exercise(actor=self.other_teacher,form=form)
        self.client.force_login(self.other_teacher)
        self.assertEqual(self.client.get(reverse('assignments:listening_exercise_create',args=[self.lesson.pk])).status_code,404)

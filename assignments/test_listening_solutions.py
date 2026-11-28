import copy
import json
import uuid
from datetime import timedelta
from unittest.mock import Mock, patch
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from django.urls import reverse
from ai_core.models import GradingJob
from ai_core.services import enqueue_submission
from dashboard.testutils import IntegratedFixture
from support.ai import context_for
from support.models import Conversation
from support.services import start_study, learner_message
from submissions.listening_review import review_groups, focused_question
from .forms import ListeningExerciseForm, ListeningSolutionsForm
from .listening import FIRST_NUMBER, LISTENING_SPECS
from .listening_solutions import extract_docx_solutions, normalize_solutions, solution_template
from .models import Lesson
from .services import assign_to_class, save_listening_exercise, save_listening_solutions
from .test_docx_import import docx, paragraph


def bundle_for(kind):
    count, start = LISTENING_SPECS[kind]['count'], FIRST_NUMBER[kind]
    return {'questions': [{'number': n, 'question_text': f'What is announced in question {n}?',
        **{'option_'+c.lower(): f'Workshop choice {c} for {n}.' for c in LISTENING_SPECS[kind]['choices']},
        'answer': 'B', 'explanation': f'PRIVATE_EXPLANATION_{n}: The guide explicitly confirms the workshop time.',
        'translation': f'Bản dịch câu {n}.'} for n in range(start, start+count)],
        'passages': [{'start': n, 'end': n+2,
            'text': f'PRIVATE_PASSAGE_{n}: W: When is the workshop?\nM: It begins after lunch.',
            'translation': f'Bản dịch đoạn {n}.'} for n in range(start, start+count, 3)] if kind in ('part3','part4') else []}


def solution_word(kind, *, relative=False, bold=False, inline=False):
    bundle = bundle_for(kind)
    lines = []
    for index, row in enumerate(bundle['questions']):
        if kind in ('part3','part4') and index % 3 == 0:
            group = bundle['passages'][index//3]
            first = index+1 if relative else group['start']
            lines.extend([f'Đoạn {first}–{first+2}', 'Nội dung: '+group['text'], 'Bản dịch: '+group['translation']])
        number = index+1 if relative else row['number']
        question = f'Câu {number}: '+row['question_text']
        if inline:
            question += ' '+ ' '.join(f'({c}) '+row['option_'+c.lower()] for c in LISTENING_SPECS[kind]['choices'])
        lines.append(question)
        if not inline:
            lines.extend(f'({c}) '+row['option_'+c.lower()] for c in LISTENING_SPECS[kind]['choices'])
        if not bold:
            lines.append('Đáp án: B')
        lines.extend(['Giải thích: '+row['explanation'], 'Bản dịch: '+row['translation']])
    body = ''.join(paragraph(line) if not (bold and line.startswith('(B)')) else
        '<w:p><w:r><w:rPr><w:b/></w:rPr><w:t>'+line+'</w:t></w:r></w:p>' for line in lines)
    return docx(body, name='solutions.docx')


class SolutionsParserTests(SimpleTestCase):
    def test_all_four_parts_import_complete_answers_and_explanations(self):
        for kind in ('part1','part2','part3','part4'):
            with self.subTest(kind=kind):
                result = extract_docx_solutions(solution_word(kind), kind)
                self.assertEqual(result, normalize_solutions(bundle_for(kind), kind))
                self.assertEqual(len(result['passages']), {'part3':13,'part4':10}.get(kind,0))

    def test_local_numbers_map_questions_and_passages_together(self):
        result = extract_docx_solutions(solution_word('part4', relative=True), 'part4')
        self.assertEqual(result['questions'][0]['number'], 71)
        self.assertEqual((result['passages'][0]['start'], result['passages'][0]['end']), (71,73))

    def test_bold_correct_answer_and_same_line_options_are_supported(self):
        self.assertEqual(extract_docx_solutions(solution_word('part2', bold=True), 'part2')['questions'][0]['answer'], 'B')
        question = extract_docx_solutions(solution_word('part3', inline=True), 'part3')['questions'][0]
        self.assertEqual(question['question_text'], bundle_for('part3')['questions'][0]['question_text'])
        self.assertEqual(question['option_d'], 'Workshop choice D for 32.')

    def test_full_word_test_selects_the_requested_part(self):
        from .docx_import import read_docx_records
        body = ''
        for kind in ('part1', 'part2', 'part3', 'part4'):
            body += paragraph('PART ' + kind[-1])
            body += ''.join(paragraph(row['text']) for row in read_docx_records(solution_word(kind)))
        for kind in ('part1', 'part2', 'part3', 'part4'):
            result = extract_docx_solutions(docx(body), kind)
            self.assertEqual(result, normalize_solutions(bundle_for(kind), kind))

    def test_word_table_cells_preserve_shared_group_and_question_boundaries(self):
        from .docx_import import read_docx_records
        rows = read_docx_records(solution_word('part4'))
        table = '<w:tbl>' + ''.join('<w:tr><w:tc>'+paragraph(row['text'])+'</w:tc></w:tr>' for row in rows) + '</w:tbl>'
        self.assertEqual(extract_docx_solutions(docx(table),'part4'), normalize_solutions(bundle_for('part4'),'part4'))

    def test_missing_explanation_choice_and_question_are_not_invented(self):
        for key in ('explanation','question_text','option_c'):
            value = bundle_for('part2'); value['questions'][4][key] = ''
            with self.subTest(field=key), self.assertRaises(ValidationError):
                normalize_solutions(value,'part2')

    def test_missing_duplicate_and_overlapping_groups_are_rejected(self):
        values = []
        value = bundle_for('part3'); value['passages'].pop(); values.append(value)
        value = bundle_for('part3'); value['passages'][1]['start'] = 32; values.append(value)
        value = bundle_for('part3'); value['passages'][0]['end'] = 35; values.append(value)
        value = bundle_for('part3'); value['passages'][0]['text'] = ''; values.append(value)
        value = bundle_for('part3'); value['questions'][1]['number'] = 32; values.append(value)
        for value in values:
            with self.assertRaises(ValidationError): normalize_solutions(value,'part3')

    def test_invalid_type_answer_range_and_oversized_data_are_rejected(self):
        values = [None, [], {'questions':[]}]
        for key, bad in [('answer','D'),('answer',[]),('number',True),('number',10000),('explanation','x'*10001)]:
            value = bundle_for('part2'); value['questions'][0][key] = bad; values.append(value)
        for value in values:
            with self.assertRaises(ValidationError): normalize_solutions(value,'part2')
        with self.assertRaises(ValidationError): normalize_solutions(bundle_for('part1'), 'invalid')

    def test_template_is_blank_and_cannot_be_imported_as_completed_solutions(self):
        for kind in ('part1','part2','part3','part4'):
            upload = SimpleUploadedFile('template.docx', solution_template(kind))
            with self.assertRaises(ValidationError): extract_docx_solutions(upload,kind)

    def test_invalid_word_and_unmarked_duplicate_questions_are_rejected(self):
        with self.assertRaises(ValidationError):
            extract_docx_solutions(SimpleUploadedFile('bad.docx', b'bad zip'), 'part2')
        body = ''.join(paragraph(line) for _ in range(2) for line in ['7. What time?', '(A) At noon.', '(B) At one.', '(C) At two.', 'Đáp án: B','Giải thích: At one.'])
        with self.assertRaises(ValidationError): extract_docx_solutions(docx(body),'part2')


class ListeningSolutionsFlowTests(IntegratedFixture):
    def setUp(self):
        super().setUp()
        self.lesson = Lesson.objects.create(skill='listening',program='B1',order=81,title='Workshop listening',created_by=self.teacher)

    def create_exercise(self, kind='part3', with_solutions=True, order=1):
        bundle = bundle_for(kind)
        data = {'kind':kind,'order':order,'question_count':LISTENING_SPECS[kind]['count']}
        if with_solutions:
            data['solution_data'] = json.dumps(bundle)
        else:
            data['answer_key'] = 'B'*LISTENING_SPECS[kind]['count']
            if kind in ('part3','part4'): data['question_data'] = json.dumps(bundle['questions'])
        files = {'audio_file': SimpleUploadedFile('audio.mp3', b'ID3-test')}
        if kind == 'part1': files['document_file'] = SimpleUploadedFile('paper.pdf',b'%PDF-1.4\n%%EOF')
        form = ListeningExerciseForm(data, files, lesson=self.lesson)
        self.assertTrue(form.is_valid(), form.errors)
        return save_listening_exercise(actor=self.teacher, form=form)

    def assign(self):
        assignment = assign_to_class(actor=self.teacher, lesson=self.lesson,classroom=self.classroom,
            assigned_at=self.now-timedelta(minutes=1),due_at=self.now+timedelta(days=1),requires_previous=False)
        return assignment.tasks.get(learner=self.student)

    def submit(self, task):
        answers = {str(q['id']):{'chosen':'A' if i==0 else 'B','short_answer':'A useful response.'}
            for i,q in enumerate(task.assignment.rubric['questions'])}
        return enqueue_submission(task=task,submission_key=uuid.uuid4().hex,answers=answers)[0]

    @patch('assignments.question_import.OpenAI')
    def test_word_preview_is_private_permission_checked_and_does_not_call_ai(self, provider):
        url = reverse('assignments:listening_solutions_extract',args=[self.lesson.pk])
        for actor, status in [(self.student,403),(self.other_teacher,404),(self.teacher,200)]:
            self.client.force_login(actor)
            response = self.client.post(url, {'kind':'part3','solutions_file':solution_word('part3')})
            self.assertEqual(response.status_code,status)
        self.assertEqual(response['Cache-Control'],'private, no-store')
        self.assertEqual(len(response.json()['solutions']['passages']),13)
        self.assertFalse(self.lesson.listening_exercises.exists())
        provider.assert_not_called()

    def test_word_upload_without_javascript_saves_full_exercise_and_keys(self):
        form = ListeningExerciseForm({'kind':'part4','order':1}, {
            'audio_file':SimpleUploadedFile('audio.mp3',b'ID3-test'), 'solutions_file':solution_word('part4')},lesson=self.lesson)
        self.assertTrue(form.is_valid(), form.errors)
        exercise = save_listening_exercise(actor=self.teacher,form=form)
        self.assertEqual(exercise.questions.first().correct_option,'B')
        self.assertEqual(exercise.questions.first().question_text,'What is announced in question 71?')
        self.assertEqual(len(exercise.solutions['passages']),10)

    def test_conflicting_manual_key_cannot_save_with_word_explanations(self):
        form = ListeningExerciseForm({'kind':'part2','order':1,'answer_key':'A'*25,
            'solution_data':json.dumps(bundle_for('part2'))}, {'audio_file':SimpleUploadedFile('audio.mp3',b'ID3-test')},lesson=self.lesson)
        self.assertFalse(form.is_valid())
        self.assertIn('solution_data', form.errors)

    def test_editing_preview_is_saved_and_unread_bad_word_cannot_reuse_old_preview(self):
        exercise = self.create_exercise('part2')
        changed = bundle_for('part2'); changed['questions'][0]['explanation'] = 'EDITED EXPLANATION'
        form = ListeningSolutionsForm({'solution_data':json.dumps(changed), 'solutions_previewed':True},
            {'solutions_file':solution_word('part2')},exercise=exercise)
        self.assertTrue(form.is_valid(),form.errors)
        self.assertEqual(form.cleaned_data['solution_bundle']['questions'][0]['explanation'], 'EDITED EXPLANATION')
        form = ListeningSolutionsForm({'solution_data':json.dumps(changed)},
            {'solutions_file':SimpleUploadedFile('bad.docx',b'not a zip')},exercise=exercise)
        self.assertFalse(form.is_valid())

    def test_solution_word_controls_question_content_for_new_exercise(self):
        value = bundle_for('part3')
        form = ListeningExerciseForm({'kind':'part3','order':1,'solution_data':json.dumps(value),
            'question_data':'[]'}, {'audio_file':SimpleUploadedFile('audio.mp3',b'ID3-test')},lesson=self.lesson)
        self.assertTrue(form.is_valid(),form.errors)
        exercise = save_listening_exercise(actor=self.teacher,form=form)
        self.assertEqual(exercise.questions.first().question_text,value['questions'][0]['question_text'])

    def test_part2_spoken_questions_answers_and_scripts_do_not_leak_before_submission(self):
        exercise = self.create_exercise('part2'); task = self.assign()
        self.assertFalse(exercise.questions.exclude(question_text='').exists())
        self.client.force_login(self.student)
        response = self.client.get(reverse('submissions:do_task',args=[task.pk]))
        for marker in ('PRIVATE_EXPLANATION_7','What is announced in question 7?','Workshop choice B for 7.'):
            self.assertNotContains(response,marker)
        job = self.submit(task)
        response = self.client.get(reverse('submissions:listening_review',args=[job.pk]))
        self.assertContains(response,'PRIVATE_EXPLANATION_7')
        self.assertContains(response,'What is announced in question 7?')
        self.assertContains(response,'Workshop choice B for 7.')
        self.assertContains(response,'Hỏi AI')

    def test_shared_passage_is_once_for_three_questions_with_individual_explanations(self):
        self.create_exercise(); task = self.assign()
        self.client.force_login(self.student)
        response = self.client.get(reverse('submissions:do_task',args=[task.pk]))
        self.assertNotContains(response,'PRIVATE_PASSAGE_32')
        self.assertNotContains(response,'PRIVATE_EXPLANATION_32')
        job = self.submit(task)
        groups = review_groups(job)
        self.assertEqual(len(groups),13)
        self.assertEqual([q['number'] for q in groups[0]['questions']], [32,33,34])
        response = self.client.get(reverse('submissions:listening_review',args=[job.pk]))
        self.assertContains(response,'PRIVATE_PASSAGE_32',count=1)
        for n in (32,33,34): self.assertContains(response,f'PRIVATE_EXPLANATION_{n}',count=1)
        self.assertNotContains(response,'PRIVATE_EXPLANATION_35')
        self.assertEqual(response['Cache-Control'],'private, no-store')
        self.assertEqual(self.client.get(reverse('submissions:listening_review',args=[job.pk]),{'group':999}).status_code,404)
        api = self.client.get(reverse('ai_core:detail',args=[job.pk]))
        self.assertNotIn('PRIVATE_EXPLANATION',api.content.decode())
        self.assertNotIn('PRIVATE_PASSAGE',api.content.decode())

    def test_unpublished_other_student_and_unrelated_teacher_cannot_read_or_ask(self):
        self.create_exercise(); task = self.assign(); job = self.submit(task)
        review = reverse('submissions:listening_review',args=[job.pk])
        question = job.rubric_snapshot['questions'][0]['id']
        ask = reverse('support:start_question',args=[job.pk,question])
        for actor in (self.other_student,self.other_teacher):
            self.client.force_login(actor)
            self.assertEqual(self.client.get(review).status_code,404)
            self.assertIn(self.client.get(ask).status_code, [403,404])
        self.client.force_login(self.student)
        job.status = 'queued'; job.save(update_fields=['status'])
        self.assertEqual(self.client.get(review).status_code,404)
        self.assertEqual(self.client.get(ask).status_code,404)
        with self.assertRaises(ValueError): review_groups(job)
        with self.assertRaises(ValidationError): start_study(self.student,job,question)

    def test_snapshot_remains_frozen_when_author_updates_later_explanation(self):
        exercise = self.create_exercise(); task = self.assign(); job = self.submit(task)
        original = copy.deepcopy(task.assignment.rubric)
        new = bundle_for('part3'); new['questions'][0]['explanation'] = 'NEW_EXPLANATION'
        save_listening_solutions(actor=self.teacher,exercise=exercise,bundle=new)
        self.assertIn('PRIVATE_EXPLANATION_32',review_groups(job)[0]['questions'][0]['explanation'])
        task.assignment.refresh_from_db(); self.assertEqual(task.assignment.rubric, original)

    def test_preexisting_assignment_can_receive_explanations_without_regrading(self):
        exercise = self.create_exercise(with_solutions=False); task = self.assign(); job = self.submit(task)
        before = (copy.deepcopy(job.result),copy.deepcopy(job.answers),job.completion_status)
        self.assertEqual(review_groups(job)[0]['questions'][0]['explanation'],'')
        save_listening_solutions(actor=self.teacher,exercise=exercise,bundle=bundle_for('part3'))
        job.refresh_from_db()
        self.assertEqual((job.result,job.answers,job.completion_status), before)
        self.assertIn('PRIVATE_EXPLANATION_32',review_groups(job)[0]['questions'][0]['explanation'])
        exercise.questions.filter(order=1).update(correct_option='A')
        self.assertEqual(review_groups(job)[0]['questions'][0]['explanation'],'')

    def test_edit_solutions_has_same_author_permissions_and_preserves_assigned_keys(self):
        exercise = self.create_exercise(); self.assign()
        url = reverse('assignments:listening_solutions_edit',args=[exercise.pk])
        for actor,status in [(self.student,403),(self.other_teacher,404),(self.teacher,200),(self.admin,200)]:
            self.client.force_login(actor); self.assertEqual(self.client.get(url).status_code,status)
        changed = bundle_for('part3'); changed['questions'][0]['answer'] = 'A'
        form = ListeningSolutionsForm({'solution_data':json.dumps(changed)},exercise=exercise)
        self.assertFalse(form.is_valid())
        with self.assertRaises(ValidationError): save_listening_solutions(actor=self.teacher,exercise=exercise,bundle=changed)
        with self.assertRaises(PermissionDenied): save_listening_solutions(actor=self.other_teacher,exercise=exercise,bundle=bundle_for('part3'))
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.post(url,{'solutions_file':solution_word('part3')}).status_code,302)

    def test_existing_exercise_cannot_attach_explanations_for_different_question_content(self):
        exercise = self.create_exercise(); self.assign()
        changed = bundle_for('part3'); changed['questions'][0]['option_a'] = 'A different option.'
        form = ListeningSolutionsForm({'solution_data':json.dumps(changed)},exercise=exercise)
        self.assertFalse(form.is_valid())
        with self.assertRaises(ValidationError): save_listening_solutions(actor=self.teacher,exercise=exercise,bundle=changed)

    def test_question_threads_are_reused_per_question_and_separate_from_general_chat(self):
        self.create_exercise(); task = self.assign(); job = self.submit(task)
        q1,q2 = job.rubric_snapshot['questions'][:2]
        first = start_study(self.student,job,q1['id'])
        self.assertEqual(first.pk,start_study(self.student,job,q1['id']).pk)
        second = start_study(self.student,job,q2['id'])
        general = start_study(self.student,job)
        self.assertEqual(len({first.pk,second.pk,general.pk}),3)
        self.assertEqual(Conversation.objects.filter(job=job).count(),3)
        with self.assertRaises(ValidationError): start_study(self.student,job,self.q1.pk)
        with self.assertRaises(PermissionDenied): start_study(self.other_student,job,q1['id'])
        self.client.force_login(self.student)
        forged = reverse('support:start_question',args=[job.pk,self.q1.pk])
        self.assertEqual(self.client.get(forged).status_code,404)
        self.assertEqual(self.client.post(forged,{'body':'Explain this question.','client_key':uuid.uuid4()}).status_code,404)

    def test_ai_receives_exact_question_explanation_and_only_its_shared_group(self):
        self.create_exercise(); task = self.assign(); job = self.submit(task)
        question = job.rubric_snapshot['questions'][1]
        thread = start_study(self.student,job,question['id'])
        context = context_for(thread)
        self.assertEqual(context['focus_question']['number'],33)
        self.assertEqual(context['focus_question']['correct_option'],'B')
        self.assertIn('PRIVATE_PASSAGE_32',context['shared_passage'])
        self.assertEqual(len(context['related_questions']),3)
        payload = json.dumps(context)
        self.assertNotIn('PRIVATE_EXPLANATION_35',payload)
        self.assertNotIn('PRIVATE_PASSAGE_35',payload)
        self.assertNotIn('questions',context)
        thread.focus_question_id = self.q1.pk
        with self.assertRaises(ValueError): context_for(thread)

    def test_focused_ai_get_is_read_only_and_submit_uses_provider_then_returns_to_group(self):
        self.create_exercise(); task = self.assign(); job = self.submit(task)
        question = job.rubric_snapshot['questions'][4]
        url = reverse('support:start_question',args=[job.pk,question['id']])
        self.client.force_login(self.student)
        page = self.client.get(url)
        self.assertContains(page,'Vì sao câu 36 chọn B?')
        self.assertContains(page,'PRIVATE_PASSAGE_35')
        self.assertFalse(Conversation.objects.filter(job=job).exists())
        with patch('support.services.OpenAITutor') as factory:
            factory.return_value.answer.return_value = {'answer':'Dựa vào thông tin về thời gian trong đoạn nghe.', 'route':'knowledge'}
            response = self.client.post(url,{'body':'Vì sao em không chọn A được?','client_key':uuid.uuid4()})
        thread = Conversation.objects.get(job=job)
        self.assertRedirects(response,thread.get_absolute_url())
        self.assertEqual(thread.focus_question_id,question['id'])
        self.assertContains(self.client.get(thread.get_absolute_url()),'group=2#question-'+str(question['id']))
        self.assertEqual(thread.messages.filter(role='assistant').count(),1)
        self.assertRedirects(self.client.get(url),thread.get_absolute_url())

    def test_html_from_word_is_escaped_on_review_and_ai_pages(self):
        exercise = self.create_exercise('part1')
        value = bundle_for('part1'); value['questions'][0]['explanation'] = '<script>alert(1)</script>'
        save_listening_solutions(actor=self.teacher,exercise=exercise,bundle=value)
        task = self.assign(); job = self.submit(task)
        self.client.force_login(self.student)
        page = self.client.get(reverse('submissions:listening_review',args=[job.pk]))
        self.assertNotContains(page,'<script>alert(1)</script>')
        self.assertContains(page,'&lt;script&gt;alert(1)&lt;/script&gt;')

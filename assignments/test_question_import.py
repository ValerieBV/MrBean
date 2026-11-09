import json
from unittest.mock import patch
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from dashboard.testutils import IntegratedFixture
from .forms import ListeningExerciseForm
from .listening import parse_answer_key
from .models import Lesson
from .question_import import extract_text_questions, extract_scanned_pdf, normalize_questions
from .services import save_listening_exercise, lesson_rubric, assign_to_class
from datetime import timedelta
from ai_core.services import enqueue_submission


def content(number):
    return {'number':number, 'question_text':f'What is happening in question {number}?',
        **{'option_'+letter.lower():f'The answer text {letter}.' for letter in 'ABCD'}, 'uncertain':False}


class PDFTextTests(SimpleTestCase):
    def test_two_column_pdf_and_wrapped_option_are_kept_in_question_order(self):
        items=[]
        for x,number in [(30,32),(330,35)]:
            for y,text in [(740,f'{number}. How do the speakers know each other?'),(720,'(A) They met through a friend.'),
                    (700,'(B) They take a class together.'),(680,'(C) They live in the same apartment'),(666,'complex.'),
                    (645,'(D) They work at the same company.')]:items.append({'x':x,'y':y,'text':text})
        rows=extract_text_questions([{'width':600,'items':items}],'part3')
        self.assertEqual([row['number'] for row in rows],[32,35])
        self.assertEqual(rows[0]['option_c'],'They live in the same apartment complex.')
        self.assertEqual(rows[1]['option_d'],'They work at the same company.')

    def test_whole_test_pdf_selects_the_requested_part(self):
        items=[]
        for n in range(1,101):
            for index,text in enumerate([f'{n}. What is question {n}?','(A) Choice A.','(B) Choice B.','(C) Choice C.','(D) Choice D.']):
                items.append({'text':text,'x':30,'y':10000-n*70-index*10})
        rows=extract_text_questions([{'width':600,'items':items}],'part4')
        self.assertEqual([row['number'] for row in rows],list(range(71,101)))

    def test_global_and_local_answer_numbers_map_to_same_order(self):
        numbers=list(range(32,71))
        for text in [' '.join(f'{n}.B' for n in numbers),' '.join(f'{n}.B' for n in range(1,40)),'B'*39]:
            rows=parse_answer_key(text,39,'ABCD',numbers)
            self.assertEqual([row['number'] for row in rows],list(range(1,40)))
            self.assertTrue(all(row['answer']=='B' for row in rows))

    def test_malformed_layout_duplicate_ids_and_missing_options_are_not_guessed(self):
        for pages in [[],[{'width':600,'items':[{'x':'bad','y':0,'text':'32. Question'}]}]]:
            with self.assertRaises(ValidationError):extract_text_questions(pages,'part3')
        with self.assertRaises(ValidationError):normalize_questions([content(32),content(32)])
        rows=extract_text_questions([{'width':600,'items':[{'text':'32. Question?','x':30,'y':700}]}],'part3')
        self.assertEqual(rows[0]['option_a'],'')

    @override_settings(OPENAI_API_KEY='test-only-key', OPENAI_TEXT_MODEL='configured-model')
    @patch('assignments.question_import.OpenAI')
    def test_scanned_pdf_uses_existing_server_key_and_structured_output(self, factory):
        client=factory.return_value.__enter__.return_value
        client.responses.create.return_value.output_text=json.dumps({'questions':[content(32)]})
        rows=extract_scanned_pdf(SimpleUploadedFile('scan.pdf',b'%PDF-1.4\n%%EOF'),'part3')
        self.assertEqual(rows[0]['number'],32)
        request=client.responses.create.call_args.kwargs
        self.assertEqual(request['model'],'configured-model');self.assertFalse(request['store'])
        self.assertTrue(request['text']['format']['strict'])
        self.assertNotIn('answer',request['text']['format']['schema']['properties']['questions']['items']['properties'])
        self.assertEqual(request['input'][0]['content'][0]['type'],'input_file')


class PDFImportWorkflowTests(IntegratedFixture):
    def setUp(self):
        super().setUp()
        self.lesson=Lesson.objects.create(skill='listening',program='B1',order=50,title='PDF question import',created_by=self.teacher)

    def test_import_form_persists_full_choices_source_numbers_and_separate_key(self):
        data={'kind':'part3','order':1,'question_count':39,'question_data':json.dumps([content(n) for n in range(32,71)]),
            'answer_key':' '.join(f'{n}.C' for n in range(32,71))}
        form=ListeningExerciseForm(data,{'audio_file':SimpleUploadedFile('audio.mp3',b'ID3-audio')},lesson=self.lesson)
        self.assertTrue(form.is_valid(),form.errors)
        exercise=save_listening_exercise(actor=self.teacher,form=form)
        question=exercise.questions.get(order=1)
        self.assertEqual(question.source_number,32);self.assertEqual(question.correct_option,'C')
        self.assertEqual(question.option_b,'The answer text B.')
        rubric=lesson_rubric(self.lesson);self.assertEqual(rubric['questions'][0]['source_number'],32)
        self.assertEqual(rubric['questions'][0]['option_d'],'The answer text D.')

    def test_letters_only_and_uncertain_content_require_teacher_correction(self):
        data={'kind':'part4','order':1,'question_count':30,'answer_key':'B'*30}
        files={'audio_file':SimpleUploadedFile('audio.mp3',b'ID3-audio')}
        form=ListeningExerciseForm(data,files,lesson=self.lesson)
        self.assertFalse(form.is_valid());self.assertIn('question_data',form.errors)
        rows=[content(n) for n in range(71,101)];rows[0]['uncertain']=True
        data['question_data']=json.dumps(rows)
        form=ListeningExerciseForm(data,files,lesson=self.lesson)
        self.assertFalse(form.is_valid());self.assertIn('Câu 71',str(form.errors))

    def test_extraction_endpoint_is_private_and_does_not_create_questions(self):
        url=reverse('assignments:listening_extract',args=[self.lesson.pk])
        body={'kind':'part3','pages':[{'width':600,'items':[{'text':'32. What happened?','x':30,'y':700}]}]}
        for actor,status in [(self.student,403),(self.other_teacher,404),(self.teacher,200)]:
            self.client.force_login(actor)
            response=self.client.post(url,body,content_type='application/json')
            self.assertEqual(response.status_code,status)
        self.assertEqual(self.lesson.questions.count(),0)
        self.assertNotIn('correct_option',response.content.decode())

    @override_settings(OPENAI_API_KEY='')
    def test_scan_without_key_returns_actionable_error_without_saving(self):
        self.client.force_login(self.teacher)
        response=self.client.post(reverse('assignments:listening_extract',args=[self.lesson.pk]),
            {'kind':'part3','document_file':SimpleUploadedFile('scan.pdf',b'%PDF-1.4\n%%EOF')})
        self.assertEqual(response.status_code,400);self.assertIn('Chưa cấu hình OpenAI',response.json()['message'])
        self.assertEqual(self.lesson.listening_exercises.count(),0)

    def test_part2_is_audio_only_and_uses_source_numbers_7_to_31(self):
        data={'kind':'part2','order':1,'question_count':25,'answer_key':' '.join(f'{n}.B' for n in range(7,32)),
            'question_data':json.dumps([content(n) for n in range(7,32)])}
        form=ListeningExerciseForm(data,{'audio_file':SimpleUploadedFile('audio.mp3',b'ID3-audio'),
            'document_file':SimpleUploadedFile('unused.pdf',b'%PDF-1.4\n%%EOF')},lesson=self.lesson)
        self.assertTrue(form.is_valid(),form.errors)
        exercise=save_listening_exercise(actor=self.teacher,form=form)
        self.assertFalse(exercise.document_file)
        self.assertEqual(list(exercise.questions.values_list('source_number',flat=True)),list(range(7,32)))
        self.assertFalse(exercise.questions.exclude(question_text='').exists())
        self.assertTrue(all(q.option_a=='A' and q.option_b=='B' and q.option_c=='C' and not q.option_d for q in exercise.questions.all()))
        self.client.force_login(self.teacher)
        response=self.client.post(reverse('assignments:listening_extract',args=[self.lesson.pk]),
            {'kind':'part2','pages':[]},content_type='application/json')
        self.assertEqual(response.status_code,400)
        self.assertIn('7–31',response.json()['message'])
        assignment=assign_to_class(actor=self.teacher,lesson=self.lesson,classroom=self.classroom,
            assigned_at=self.now-timedelta(minutes=1),due_at=self.now+timedelta(days=1),requires_previous=False)
        task=assignment.tasks.get(learner=self.student)
        self.client.force_login(self.student)
        page=self.client.get(reverse('submissions:do_task',args=[task.pk]))
        self.assertEqual([q['number'] for q in page.context['questions']],list(range(7,32)))
        self.assertNotContains(page,'data-pdf-url')
        answers={str(q.pk):{'chosen':'B','short_answer':'The answer I heard.'} for q in exercise.questions.all()}
        job,_=enqueue_submission(task=task,submission_key='part2-audio-only',answers=answers)
        self.assertIsNone(job.final_score)
        page=self.client.get(reverse('submissions:result',args=[job.pk]))
        self.assertEqual([q['number'] for q in page.context['listening_details']],list(range(7,32)))
        # Old snapshots lack source_number; their public numbering still follows the selected part.
        assignment.rubric['questions']=[{k:v for k,v in q.items() if k!='source_number'} for q in assignment.rubric['questions']]
        assignment.save(update_fields=['rubric'])
        page=self.client.get(reverse('submissions:do_task',args=[task.pk]))
        self.assertEqual(page.context['questions'][0]['number'],7)

    def test_part4_requires_source_numbers_71_to_100(self):
        data={'kind':'part4','order':1,'question_count':30,'answer_key':'B'*30,
            'question_data':json.dumps([content(n) for n in range(1,31)])}
        form=ListeningExerciseForm(data,{'audio_file':SimpleUploadedFile('audio.mp3',b'ID3-audio')},lesson=self.lesson)
        self.assertFalse(form.is_valid());self.assertIn('71–100',str(form.errors))

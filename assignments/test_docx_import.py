import io
import json
import zipfile
from datetime import timedelta
from html import escape
from unittest.mock import patch
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from dashboard.testutils import IntegratedFixture
from .docx_import import extract_docx_questions
from .question_import import extract_text_questions, parse_lines
from .forms import ListeningExerciseForm
from .models import Lesson
from .services import assign_to_class, save_listening_exercise

NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'


def paragraph(text, props=''):
    return f'<w:p>{props}<w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>'


def question(number):
    return [f'{number}. What does the man need to do first?', '(A) Change his clothes.',
            '(B) Attach a name tag.', '(C) Contact a warehouse supervisor.', '(D) Read an employee handbook.']


def docx(body, *, numbering=None, styles=None, name='questions.docx', extra=None):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('word/document.xml', f'<w:document xmlns:w="{NS}"><w:body>{body}</w:body></w:document>')
        for filename, text in [('word/numbering.xml', numbering), ('word/styles.xml', styles), *(extra or [])]:
            if text is not None:
                archive.writestr(filename, text)
    return SimpleUploadedFile(name, output.getvalue())


def plain_docx(start, count):
    return docx(''.join(paragraph(line) for n in range(start, start+count) for line in question(n)))


class WordImportTests(SimpleTestCase):
    def test_plain_word_reads_all_39_questions_and_printed_choices(self):
        rows = extract_docx_questions(plain_docx(32, 39), 'part3')
        self.assertEqual([r['number'] for r in rows], list(range(32, 71)))
        self.assertEqual(rows[0]['option_b'], 'Attach a name tag.')
        self.assertFalse(any(r['uncertain'] for r in rows))

    def test_automatic_nested_question_and_letter_numbering_is_read(self):
        numbering = f'''<w:numbering xmlns:w="{NS}"><w:abstractNum w:abstractNumId="0">
            <w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/></w:lvl>
            <w:lvl w:ilvl="1"><w:start w:val="1"/><w:numFmt w:val="upperLetter"/><w:lvlText w:val="(%2)"/></w:lvl>
            </w:abstractNum><w:num w:numId="1"><w:abstractNumId w:val="0"/>
            <w:lvlOverride w:ilvl="0"><w:startOverride w:val="71"/></w:lvlOverride></w:num></w:numbering>'''
        body = ''
        for n in range(30):
            for level, text in [(0, 'Where is the speaker?'), *[(1, f'At location {c}.') for c in 'ABCD']]:
                body += paragraph(text, f'<w:pPr><w:numPr><w:ilvl w:val="{level}"/><w:numId w:val="1"/></w:numPr></w:pPr>')
        rows = extract_docx_questions(docx(body, numbering=numbering), 'part4')
        self.assertEqual([r['number'] for r in rows], list(range(71, 101)))
        self.assertTrue(all(r['option_d'] == 'At location D.' for r in rows))

    def test_style_numbering_and_local_1_to_30_are_mapped_to_part4(self):
        numbering = f'<w:numbering xmlns:w="{NS}"><w:abstractNum w:abstractNumId="0"><w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/></w:lvl></w:abstractNum><w:num w:numId="2"><w:abstractNumId w:val="0"/></w:num></w:numbering>'
        styles = f'<w:styles xmlns:w="{NS}"><w:style w:styleId="Question"><w:pPr><w:numPr><w:numId w:val="2"/></w:numPr></w:pPr></w:style></w:styles>'
        body = ''.join(paragraph('What is the purpose of the message?', '<w:pPr><w:pStyle w:val="Question"/><w:numPr><w:ilvl w:val="0"/></w:numPr></w:pPr>')+
            ''.join(paragraph(line) for line in question(1)[1:]) for _ in range(30))
        rows = extract_docx_questions(docx(body, numbering=numbering, styles=styles), 'part4')
        self.assertEqual([r['number'] for r in rows], list(range(71, 101)))

    def test_line_breaks_and_lowercase_options_are_read(self):
        body = '<w:p><w:r>' + ''.join('<w:t>'+escape(line)+'</w:t><w:br/>' for line in ['Question 71 : Who is speaking?', '(a) A guide.', '(b) A clerk.', '(c) A manager.', '(d) A guest.']) + '</w:r></w:p>'
        row = extract_docx_questions(docx(body), 'part4')[0]
        self.assertEqual(row['question_text'], 'Who is speaking?')
        self.assertEqual(row['option_b'], 'A clerk.')

    def test_two_column_table_with_separate_option_rows_keeps_columns_together(self):
        left, right = question(32), question(35)
        table = '<w:tbl>'+''.join('<w:tr><w:tc>'+paragraph(a)+'</w:tc><w:tc>'+paragraph(b)+'</w:tc></w:tr>' for a, b in zip(left, right))+'</w:tbl>'
        rows = extract_docx_questions(docx(table), 'part3')
        self.assertEqual([r['number'] for r in rows], [32,35])
        self.assertTrue(all(r['option_b'] == 'Attach a name tag.' for r in rows))

    def test_whole_word_test_selects_only_requested_part(self):
        rows = extract_docx_questions(plain_docx(1, 100), 'part4')
        self.assertEqual([r['number'] for r in rows], list(range(71,101)))

    def test_image_only_and_legacy_doc_have_actionable_errors(self):
        for upload, message in [(docx('<w:p><w:r><w:drawing/></w:r></w:p>'), 'không có văn bản'),
                                (plain_docx(71,30), '.docx')]:
            if message == '.docx':
                upload.name = 'old.doc'
            with self.assertRaisesMessage(ValidationError, message):
                extract_docx_questions(upload, 'part4')

    def test_invalid_zip_dtd_and_oversized_xml_are_rejected(self):
        files = [SimpleUploadedFile('bad.docx', b'not a zip'),
                 docx('', extra=[('word/styles.xml', '<!DOCTYPE x [<!ENTITY bomb "text">]><x/>')]),
                 docx('', extra=[('word/styles.xml', 'x'*(2*1024*1024+1))])]
        for upload in files:
            with self.subTest(name=upload.name), self.assertRaises(ValidationError):
                extract_docx_questions(upload, 'part4')

    def test_more_pdf_number_and_option_styles_and_fragmented_number_are_read(self):
        page = {'width':600, 'items':[{'text':t,'x':x,'y':y} for x,y,t in [(30,740,'32'),(45,740,'.'),(55,740,'What time does it begin?'),
            (30,720,'a: At 4:00.'),(30,700,'b) At 5:00.'),(30,680,'c. At 6:00.'),(30,660,'d) At 7:00.')]]}
        row = extract_text_questions([page], 'part3')[0]
        self.assertEqual(row['question_text'], 'What time does it begin?')
        self.assertEqual(row['option_b'], 'At 5:00.')
        rows = parse_lines(['32. What time?', '(A) Before', '5:00 P.M.', '(B) After 6:00.'])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['option_a'], 'Before 5:00 P.M.')


class WordEndpointTests(IntegratedFixture):
    def setUp(self):
        super().setUp()
        self.lesson = Lesson.objects.create(skill='listening', program='B1', order=71, title='Word import', created_by=self.teacher)
        self.url = reverse('assignments:listening_extract', args=[self.lesson.pk])

    @override_settings(OPENAI_API_KEY='')
    @patch('assignments.question_import.OpenAI')
    def test_word_does_not_call_openai_and_respects_lesson_permissions(self, provider):
        for actor, status in [(self.student,403), (self.other_teacher,404), (self.teacher,200)]:
            self.client.force_login(actor)
            response = self.client.post(self.url, {'kind':'part4', 'docx_file':plain_docx(71,30)})
            self.assertEqual(response.status_code, status)
        provider.assert_not_called()
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        self.assertEqual(len(response.json()['questions']), 30)
        self.assertFalse(self.lesson.questions.exists())

    def test_word_content_saves_without_pdf_and_is_available_to_learner(self):
        self.client.force_login(self.teacher)
        rows = self.client.post(self.url, {'kind':'part4','docx_file':plain_docx(71,30)}).json()['questions']
        form = ListeningExerciseForm({'kind':'part4','order':1,'question_count':30,
            'question_data':json.dumps(rows),'answer_key':'B'*30}, {'audio_file':SimpleUploadedFile('audio.mp3',b'ID3-audio')}, lesson=self.lesson)
        self.assertTrue(form.is_valid(), form.errors)
        exercise = save_listening_exercise(actor=self.teacher, form=form)
        self.assertFalse(exercise.document_file)
        assignment = assign_to_class(actor=self.teacher,lesson=self.lesson,classroom=self.classroom,
            assigned_at=self.now-timedelta(minutes=1),due_at=self.now+timedelta(days=1),requires_previous=False)
        task = assignment.tasks.get(learner=self.student)
        self.client.force_login(self.student)
        page = self.client.get(reverse('submissions:do_task',args=[task.pk]))
        self.assertContains(page,'Attach a name tag.')
        self.assertEqual([q['number'] for q in page.context['questions']],list(range(71,101)))
        self.assertNotContains(page,'data-pdf-url')
        self.client.force_login(self.teacher)
        response = self.client.post(self.url, {'kind':'part4','docx_file':plain_docx(71,30)})
        self.assertEqual(response.status_code,409)

    def test_docx_import_is_not_available_for_audio_only_part2(self):
        self.client.force_login(self.teacher)
        response = self.client.post(self.url, {'kind':'part2','docx_file':plain_docx(7,25)})
        self.assertEqual(response.status_code,400)
        self.assertIn('chỉ dùng file nghe',response.json()['message'])

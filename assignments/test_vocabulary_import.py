import io
import time
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from django import forms
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template.defaultfilters import linebreaksbr
from django.test import Client, SimpleTestCase
from django.urls import reverse

from dashboard.testutils import IntegratedFixture
from .forms import VocabularyImportForm, VocabWordForm
from .models import Lesson, VocabWord
from .services import assign_to_class, import_vocabulary_rows
from .vocabulary_import import parse_vocabulary_text


FULL_ENTRIES_CSV = Path(__file__).with_name('testdata') / 'vocabulary_full_entries.csv'


class VocabularyParserTests(SimpleTestCase):
    def test_full_entries_csv_preserves_all_ten_words_and_multiple_senses(self):
        rows = parse_vocabulary_text(FULL_ENTRIES_CSV.read_text(encoding='utf-8-sig'), csv_file=True)
        self.assertEqual([row['word'] for row in rows], ['department', 'issue', 'corporate', 'sign up',
            'outing', 'notify', 'supervisor', 'join', 'appliance', 'purchase'])
        self.assertEqual(rows[7]['meaning'].count('\n- '), 3)
        self.assertIn('/dzoin/', rows[7]['meaning'])
        self.assertEqual(rows[9]['word_type'], 'v / n')
        self.assertIn("(v) /'p3:rtfas/: to buy sth\n(n)", rows[9]['meaning'])
        self.assertTrue(all(row['example'] == '' for row in rows))

    def test_plain_words_phrases_and_numbered_lines_need_no_meaning(self):
        rows = parse_vocabulary_text('word\n\n1. department\n2) sign up\nissue\n')
        self.assertEqual([row['word'] for row in rows], ['word', 'department', 'sign up', 'issue'])
        self.assertEqual(rows[1]['line'], 3)
        self.assertTrue(all(row['meaning'] == '' for row in rows))

    def test_excel_tabs_pipe_and_semicolon_support_optional_columns(self):
        for text in ('department\tbộ phận', 'department | bộ phận', 'department;bộ phận'):
            with self.subTest(text=text):
                row = parse_vocabulary_text(text)[0]
                self.assertEqual(row['word'], 'department')
                self.assertEqual(row['meaning'], 'bộ phận')
        row = parse_vocabulary_text('sign up\tv\tđăng ký\tPlease sign up.')[0]
        self.assertEqual((row['word_type'], row['meaning'], row['example']), ('v', 'đăng ký', 'Please sign up.'))
        self.assertEqual(parse_vocabulary_text('issue | n | vấn đề')[0]['meaning'], 'vấn đề')
        mixed = parse_vocabulary_text('department\nissue | vấn đề')
        self.assertEqual(mixed[0]['meaning'], '')
        self.assertEqual(mixed[1]['word'], 'issue')
        self.assertEqual(mixed[1]['meaning'], 'vấn đề')

    def test_headers_allow_reordered_vietnamese_columns_and_index(self):
        rows = parse_vocabulary_text('STT\tNghĩa\tTừ vựng\tLoại từ\tVí dụ\n12\tbộ phận\tdepartment\tn\tSales department.')
        self.assertEqual(rows[0]['word'], 'department')
        self.assertEqual(rows[0]['meaning'], 'bộ phận')
        self.assertNotIn('order', rows[0])

    def test_utf8_bom_csv_quotes_commas_multiline_and_trailing_optional_columns(self):
        rows = parse_vocabulary_text('\ufeffword,word_type,meaning,example\r\nissue,n,"vấn đề, chủ đề","First line\nsecond line"\r\nsign up,v\r\n', csv_file=True)
        self.assertEqual(rows[0]['meaning'], 'vấn đề, chủ đề')
        self.assertEqual(rows[0]['example'], 'First line\nsecond line')
        self.assertEqual(rows[1]['meaning'], '')
        self.assertEqual(parse_vocabulary_text('word\ndepartment\n', csv_file=True)[0]['word'], 'department')
        self.assertEqual(parse_vocabulary_text('word\n"hello, world"\n', csv_file=True)[0]['word'], 'hello, world')

    def test_empty_invalid_oversized_and_unsupported_rows_fail(self):
        cases = ['', '\n ', 'word,meaning\n,missing word', 'word,word\nx,y',
            'word,meaning,notes\nx,y,z', 'a|b|c|d|e|f', 'x' * 121,
            'a|n|' + 'x' * 256, 'a\x00b', 'x' * 150000, 'x' * 250001,
            '\n'.join('word' + str(i) for i in range(501)), 'word,meaning\na,"unclosed']
        for text in cases:
            with self.subTest(text=text[:60]):
                with self.assertRaises(ValidationError):
                    parse_vocabulary_text(text)

    def test_file_validation_and_two_input_sources(self):
        for filename, content in [('words.xlsx', b'not-an-excel-parser'), ('words.csv', b'\xff\xfe'),
                                  ('empty.txt', b''), ('large.txt', b'x' * (1024 * 1024 + 1))]:
            form = VocabularyImportForm({}, {'upload': SimpleUploadedFile(filename, content)})
            self.assertFalse(form.is_valid(), filename)
        both = VocabularyImportForm({'text': 'hello'}, {'upload': SimpleUploadedFile('words.txt', b'world')})
        self.assertFalse(both.is_valid())
        self.assertFalse(VocabularyImportForm({}).is_valid())
        self.assertFalse(VocabularyImportForm({'text': '\tmissing word'}).is_valid())


class VocabularyImportTests(IntegratedFixture):
    def setUp(self):
        super().setUp()
        self.lesson = Lesson.objects.create(skill='vocabulary', program='B1', order=45,
            title='Từ vựng nhập hàng loạt', created_by=self.teacher)
        self.url = reverse('assignments:vocabulary_import', args=[self.lesson.pk])
        self.client.force_login(self.teacher)

    def preview(self, text='department\nissue\nsign up'):
        response = self.client.post(self.url, {'action': 'preview', 'text': text})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['preview_token'])
        return response

    def confirm(self, token, client=None, url=None):
        return (client or self.client).post(url or self.url, {'action': 'confirm', 'preview_token': token})

    def test_full_entries_survive_import_edit_assignment_and_png_submission(self):
        upload = SimpleUploadedFile('tu_vung.csv', FULL_ENTRIES_CSV.read_bytes(), content_type='text/csv')
        response = self.client.post(self.url, {'action': 'preview', 'upload': upload})
        self.assertEqual(response.context['add_count'], 10)
        self.assertEqual(response.context['skip_count'], 0)
        self.assertEqual(self.lesson.words.count(), 0)
        for row in response.context['preview']:
            self.assertContains(response, linebreaksbr(row['meaning']))
        self.confirm(response.context['preview_token'])
        purchase = self.lesson.words.get(word='purchase')
        self.assertEqual(purchase.word_type, 'v / n')
        self.assertEqual(self.lesson.words.count(), 10)
        edit_url = reverse('assignments:item_edit', args=['vocabulary', purchase.pk])
        edit = self.client.get(edit_url)
        self.assertIsInstance(edit.context['form'].fields['meaning'].widget, forms.Textarea)
        self.assertEqual(edit.context['form']['meaning'].value(), purchase.meaning)
        self.assertRedirects(self.client.post(edit_url, {'order': purchase.order, 'word': purchase.word,
            'word_type': purchase.word_type, 'meaning': purchase.meaning, 'example': ''}),
            reverse('assignments:lesson_detail', args=[self.lesson.pk]))
        purchase.refresh_from_db()
        self.assertIn('\n(n)', purchase.meaning)
        self.assertContains(self.client.get(reverse('assignments:lesson_detail', args=[self.lesson.pk])),
            linebreaksbr(purchase.meaning))
        assigned = assign_to_class(actor=self.teacher, lesson=self.lesson, classroom=self.classroom,
            assigned_at=self.now - timedelta(minutes=1), due_at=self.now + timedelta(days=1),
            repetitions=1, requires_previous=False)
        self.assertEqual(len(assigned.rubric['words']), 10)
        self.assertIn('sign up', assigned.rubric['words'])
        detail = next(row for row in assigned.rubric['word_details'] if row['word'] == 'purchase')
        self.assertEqual(detail['meaning'], purchase.meaning)
        self.assertEqual(detail['word_type'], 'v / n')
        task = assigned.tasks.get(learner=self.student)
        self.client.force_login(self.student)
        response = self.client.get(reverse('submissions:do_task', args=[task.pk]))
        self.assertContains(response, linebreaksbr(purchase.meaning))
        self.assertContains(response, '10. purchase')
        self.assertContains(response, 'Bài có 10 từ / cụm từ.')
        stream = io.BytesIO()
        Image.new('RGB', (80, 60), 'white').save(stream, 'PNG')
        response = self.client.post(reverse('ai_core:submit'), {'task_id': task.pk,
            'submission_key': 'csv-import-png', 'reference_version': assigned.reference_version,
            'images': SimpleUploadedFile('bai_lam.png', stream.getvalue(), content_type='image/png')})
        self.assertEqual(response.status_code, 201)
        job = task.jobs.get()
        self.assertEqual(job.status, 'queued')
        self.assertEqual(job.pages.count(), 1)
        self.assertEqual(job.rubric_snapshot, assigned.rubric)

    def test_multiline_definitions_are_escaped_on_every_reading_screen(self):
        definition = 'First meaning\n<script>alert(1)</script>\nSecond meaning'
        response = self.preview('word,word_type,meaning,example\njoin,v,"' + definition + '",')
        self.assertContains(response, linebreaksbr(definition))
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.confirm(response.context['preview_token'])
        assigned = assign_to_class(actor=self.teacher, lesson=self.lesson, classroom=self.classroom,
            assigned_at=self.now - timedelta(minutes=1), due_at=self.now + timedelta(days=1), requires_previous=False)
        for actor, url in [(self.teacher, reverse('assignments:lesson_detail', args=[self.lesson.pk])),
                (self.student, reverse('submissions:do_task', args=[assigned.tasks.get(learner=self.student).pk]))]:
            self.client.force_login(actor)
            response = self.client.get(url)
            self.assertContains(response, linebreaksbr(definition))
            self.assertNotContains(response, '<script>alert(1)</script>')

    def test_preview_has_no_writes_and_confirm_makes_words_available_to_assignment(self):
        self.assertContains(self.client.get(reverse('assignments:lesson_detail', args=[self.lesson.pk])), self.url)
        response = self.preview()
        self.assertEqual(self.lesson.words.count(), 0)
        self.assertEqual(response.context['add_count'], 3)
        self.assertRedirects(self.confirm(response.context['preview_token']),
            reverse('assignments:lesson_detail', args=[self.lesson.pk]))
        self.assertEqual(list(self.lesson.words.values_list('word', 'order')), [('department', 1), ('issue', 2), ('sign up', 3)])
        assigned = assign_to_class(actor=self.teacher, lesson=self.lesson, classroom=self.classroom,
            assigned_at=self.now, due_at=self.now + timedelta(days=1), repetitions=4)
        self.assertEqual(assigned.rubric['words'], ['department', 'issue', 'sign up'])
        self.assertEqual(assigned.rubric['repetitions'], 4)
        self.assertEqual(assigned.tasks.count(), 1)

    def test_duplicates_are_previewed_skipped_and_do_not_overwrite_existing_words(self):
        existing = VocabWord.objects.create(lesson=self.lesson, word='Department', meaning='Nghĩa gốc', order=7)
        response = self.preview('department | Nghĩa khác\nSign up | đăng ký\nsign   up | lặp\nissue | vấn đề')
        self.assertEqual(response.context['add_count'], 2)
        self.assertEqual(response.context['skip_count'], 2)
        token = response.context['preview_token']
        self.confirm(token)
        existing.refresh_from_db()
        self.assertEqual(existing.meaning, 'Nghĩa gốc')
        self.assertEqual(list(self.lesson.words.values_list('order', flat=True)), [7, 8, 9])
        self.confirm(token)
        self.assertEqual(self.lesson.words.count(), 3)

    def test_csv_upload_preview_and_confirm_do_not_require_uploading_again(self):
        upload = SimpleUploadedFile('tu_vung.csv', '\ufeffword,word_type,meaning,example\ndepartment,n,bộ phận,Sales department.\nissue,,,\n'.encode())
        response = self.client.post(self.url, {'action': 'preview', 'upload': upload})
        self.assertEqual(response.context['add_count'], 2)
        self.confirm(response.context['preview_token'])
        self.assertEqual(self.lesson.words.get(word='department').meaning, 'bộ phận')
        self.assertEqual(self.lesson.words.get(word='issue').meaning, '')

    def test_all_duplicates_disable_confirmation_button(self):
        VocabWord.objects.create(lesson=self.lesson, word='department')
        response = self.preview('DEPARTMENT')
        self.assertEqual(response.context['add_count'], 0)
        self.assertContains(response, 'Tất cả từ trong danh sách đã có')
        self.assertNotContains(response, 'name="action" value="confirm"')

    def test_invalid_batch_makes_no_partial_changes(self):
        response = self.client.post(self.url, {'action': 'preview', 'text': 'good\n' + 'x' * 121})
        self.assertTrue(response.context['form'].errors)
        self.assertEqual(self.lesson.words.count(), 0)
        with self.assertRaises(ValidationError):
            import_vocabulary_rows(actor=self.teacher, lesson=self.lesson, rows=[{'word': 'good'}, {'word': ''}])
        self.assertEqual(self.lesson.words.count(), 0)

    def test_confirmation_rechecks_duplicates_added_since_preview(self):
        token = self.preview('department\nissue').context['preview_token']
        VocabWord.objects.create(lesson=self.lesson, word='department', order=20, meaning='Giữ lại')
        self.confirm(token)
        self.assertEqual(self.lesson.words.count(), 2)
        self.assertEqual(self.lesson.words.get(word='issue').order, 21)

    def test_permissions_and_lesson_type_are_enforced(self):
        for actor, status in ((self.student, 403), (self.other_teacher, 404)):
            self.client.force_login(actor)
            for data in (None, {'action': 'preview', 'text': 'hello'}, {'action': 'confirm', 'preview_token': 'bad'}):
                response = self.client.get(self.url) if data is None else self.client.post(self.url, data)
                self.assertEqual(response.status_code, status)
            with self.assertRaises(PermissionDenied):
                import_vocabulary_rows(actor=actor, lesson=self.lesson, rows=[{'word': 'hello'}])
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('assignments:vocabulary_import', args=[self.speaking.pk])).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_admin_and_manager_can_import_in_lessons_created_by_teacher(self):
        for actor in (self.admin, self.manager):
            self.client.force_login(actor)
            token = self.preview(actor.username).context['preview_token']
            self.assertEqual(self.confirm(token).status_code, 302)
        self.assertEqual(self.lesson.words.count(), 2)

    def test_tampered_expired_actor_and_lesson_tokens_are_rejected(self):
        token = self.preview().context['preview_token']
        self.assertContains(self.confirm(token + 'bad'), 'không hợp lệ')
        with patch('django.core.signing.time.time', return_value=time.time() + 1900):
            self.assertContains(self.confirm(token), 'quá 30 phút')
        other_lesson = Lesson.objects.create(skill='vocabulary', program='B1', order=46,
            title='Buổi khác', created_by=self.teacher)
        self.assertContains(self.confirm(token, url=reverse('assignments:vocabulary_import', args=[other_lesson.pk])), 'không hợp lệ')
        self.client.force_login(self.admin)
        self.assertContains(self.confirm(token), 'không hợp lệ')
        self.assertEqual(self.lesson.words.count(), 0)
        self.assertEqual(other_lesson.words.count(), 0)

    def test_publishing_after_preview_blocks_confirmation_and_preserves_snapshot(self):
        token = self.preview().context['preview_token']
        VocabWord.objects.create(lesson=self.lesson, word='original')
        assigned = assign_to_class(actor=self.teacher, lesson=self.lesson, classroom=self.classroom,
            assigned_at=self.now, due_at=self.now + timedelta(days=1))
        self.assertRedirects(self.confirm(token), reverse('assignments:lesson_detail', args=[self.lesson.pk]))
        assigned.refresh_from_db()
        self.assertEqual(assigned.rubric['words'], ['original'])
        self.assertEqual(self.lesson.words.count(), 1)
        self.assertNotContains(self.client.get(reverse('assignments:lesson_detail', args=[self.lesson.pk])), self.url)

    def test_csrf_required_and_other_methods_cannot_import(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.teacher)
        client.get(self.url)
        self.assertEqual(client.post(self.url, {'text': 'hello'}).status_code, 403)
        for method in ('put', 'patch', 'delete'):
            self.assertEqual(getattr(self.client, method)(self.url).status_code, 405)
        token = self.preview('hello').context['preview_token']
        csrf = client.cookies['csrftoken'].value
        response = client.post(self.url, {'action': 'confirm', 'preview_token': token}, HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.lesson.words.count(), 1)

    def test_preview_escapes_untrusted_text(self):
        response = self.preview('<script>alert(1)</script> | <b>nghĩa</b>')
        self.assertContains(response, '&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertNotContains(response, '<script>alert(1)</script>')

    def test_single_word_form_also_accepts_optional_meaning(self):
        form = VocabWordForm({'order': 1, 'word': 'department', 'word_type': '', 'meaning': '', 'example': ''})
        self.assertTrue(form.is_valid(), form.errors)

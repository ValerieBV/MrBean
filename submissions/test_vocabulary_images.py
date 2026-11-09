from django.urls import reverse

from dashboard.services import annotated_tasks
from dashboard.testutils import IntegratedFixture
from ai_core.models import GradingJob


class VocabularyImageSubmissionTests(IntegratedFixture):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.student)

    def submit(self, key, **extra):
        return self.client.post(reverse('ai_core:submit'), {
            'task_id': self.vocab_task.pk, 'submission_key': key,
            'reference_version': self.vocab_task.assignment.reference_version, **extra})

    def test_new_submissions_require_images_even_when_text_is_supplied(self):
        for key, extra in [('empty', {}), ('typed', {'text': 'Customer Deadline'})]:
            response = self.submit(key, **extra)
            self.assertEqual(response.status_code, 400)
            self.assertIn('ít nhất 1 ảnh', response.json()['message'])
        self.assertFalse(GradingJob.objects.exists())
        response = self.submit('too-many', images=[self.vocabulary_image() for _ in range(6)])
        self.assertEqual(response.status_code, 400)
        self.assertIn('Tối đa 5 ảnh', response.json()['message'])
        self.assertFalse(GradingJob.objects.exists())

    def test_image_upload_ignores_old_form_text_and_retries_do_not_duplicate(self):
        response = self.submit('photo', images=[self.vocabulary_image()], text='Text from an old form')
        self.assertEqual(response.status_code, 201, response.content)
        job = GradingJob.objects.get()
        self.assertEqual((job.kind, job.status, job.text), ('vocabulary', 'queued', ''))
        self.assertEqual(job.pages.count(), 1)
        self.assertEqual(self.submit('photo').status_code, 200)
        self.assertEqual(GradingJob.objects.count(), 1)
        self.assertEqual(job.pages.count(), 1)

    def test_form_has_only_image_input_and_does_not_restore_old_text_drafts(self):
        self.vocab_task.draft = {'text': 'OLD_TYPED_DRAFT'}
        self.vocab_task.draft_saved_at = self.now
        self.vocab_task.save(update_fields=['draft', 'draft_saved_at'])
        response = self.client.get(reverse('submissions:do_task', args=[self.vocab_task.pk]))
        for content in ['Nộp bài từ vựng bằng ảnh', 'id="chooseImages"', 'id="imagePreviews"']:
            self.assertContains(response, content)
        for content in ['<textarea', 'OLD_TYPED_DRAFT', 'data-draft-url=', 'id="draftStatus"']:
            self.assertNotContains(response, content)
        self.assertFalse(annotated_tasks(self.student).get(pk=self.vocab_task.pk).has_draft)
        response = self.client.post(reverse('submissions:autosave', args=[self.vocab_task.pk]),
            {'text': 'New typed draft', 'reference_version': self.vocab_task.assignment.reference_version},
            content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], 'images_only')
        self.vocab_task.refresh_from_db()
        self.assertEqual(self.vocab_task.draft['text'], 'OLD_TYPED_DRAFT')

    def test_past_text_submissions_remain_readable(self):
        job = GradingJob.objects.create(task=self.vocab_task, submission_key='legacy-text',
            kind='vocabulary', text='PAST_VOCABULARY_WORK', rubric_snapshot=self.vocab_task.assignment.rubric)
        self.assertContains(self.client.get(reverse('submissions:result', args=[job.pk])), 'PAST_VOCABULARY_WORK')

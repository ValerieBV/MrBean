import os
from datetime import timedelta
from io import StringIO

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.db import transaction
from django.utils import timezone

from accounts.services import delete_user_account
from ai_core.models import GradingJob, VocabularyPage
from dashboard.testutils import IntegratedFixture
from submissions.models import LessonProgress, SpeakingRecording


class SubmissionFileCleanupTests(IntegratedFixture):
    def job(self, key):
        return GradingJob.objects.create(task=self.task, kind='speaking', submission_key=key,
            audio=ContentFile(b'audio', name='recording.webm'))

    def test_account_deletion_removes_all_owned_submission_files_after_commit(self):
        job = self.job('owned-recording')
        page = VocabularyPage.objects.create(job=job, image=ContentFile(b'image', name='page.jpg'))
        progress = LessonProgress.objects.create(student=self.student, lesson=self.speaking)
        recording = SpeakingRecording.objects.create(progress=progress, task=self.speaking.speaking_tasks.first(),
            audio=ContentFile(b'legacy recording', name='legacy.wav'))
        names = [job.audio.name, page.image.name, recording.audio.name]
        with self.captureOnCommitCallbacks(execute=True):
            delete_user_account(actor=self.admin, user_id=self.student.pk)
            self.assertTrue(all(default_storage.exists(name) for name in names))
        self.assertTrue(all(not default_storage.exists(name) for name in names))

    def test_bulk_job_delete_also_cleans_audio_and_pages(self):
        job = self.job('bulk')
        page = VocabularyPage.objects.create(job=job, image=ContentFile(b'image', name='page.jpg'))
        names = [job.audio.name, page.image.name]
        with self.captureOnCommitCallbacks(execute=True):
            GradingJob.objects.filter(pk=job.pk).delete()
        self.assertTrue(all(not default_storage.exists(name) for name in names))

    def test_shared_file_is_kept_until_last_submission_reference_is_deleted(self):
        first = self.job('shared-first')
        name = first.audio.name
        second = GradingJob.objects.create(task=self.task, kind='speaking', submission_key='shared-second', audio=name)
        with self.captureOnCommitCallbacks(execute=True):
            first.delete()
        self.assertTrue(default_storage.exists(name))
        with self.captureOnCommitCallbacks(execute=True):
            second.delete()
        self.assertFalse(default_storage.exists(name))

    def test_rollback_retains_database_and_file(self):
        job = self.job('rollback')
        job_id, name = job.pk, job.audio.name
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(ValueError):
                with transaction.atomic():
                    job.delete()
                    raise ValueError('rollback')
        self.assertTrue(GradingJob.objects.filter(pk=job_id).exists())
        self.assertTrue(default_storage.exists(name))

    def test_deleting_account_with_protected_cross_user_link_keeps_files(self):
        from django.core.exceptions import ValidationError
        from support.models import Conversation
        job = self.job('protected-file')
        name = job.audio.name
        Conversation.objects.create(student=self.other_student, job=job, kind='contact',
            subject='Protected reference', recipient=self.teacher, recipient_role='teacher')
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(ValidationError):
                delete_user_account(actor=self.admin, user_id=self.student.pk)
        self.assertTrue(default_storage.exists(name))

    def test_cleanup_command_previews_old_orphans_and_preserves_live_and_recent_files(self):
        job = self.job('live')
        orphan = default_storage.save('ai_submissions/orphan.wav', ContentFile(b'orphan'))
        old_recording = default_storage.save('submissions/recordings/orphan.wav', ContentFile(b'legacy orphan'))
        recent = default_storage.save('ai_submissions/recent.wav', ContentFile(b'upload in progress'))
        lesson_file = default_storage.save('lessons/keep.mp3', ContentFile(b'lesson'))
        old = (timezone.now()-timedelta(days=2)).timestamp()
        for name in (orphan, old_recording, job.audio.name, lesson_file):
            os.utime(default_storage.path(name), (old, old))
        output = StringIO()
        call_command('cleanup_submission_files', stdout=output)
        self.assertIn('File mồ côi: 2; đã xóa: 0.', output.getvalue())
        self.assertTrue(default_storage.exists(orphan))
        output = StringIO()
        call_command('cleanup_submission_files', delete=True, stdout=output)
        self.assertIn('File mồ côi: 2; đã xóa: 2.', output.getvalue())
        self.assertFalse(default_storage.exists(orphan))
        self.assertFalse(default_storage.exists(old_recording))
        for name in (job.audio.name, recent, lesson_file):
            self.assertTrue(default_storage.exists(name))

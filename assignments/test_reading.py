from datetime import timedelta
from django.core.exceptions import ValidationError
from django.urls import reverse
from dashboard.testutils import IntegratedFixture
from ai_core.models import GradingJob
from ai_core.services import enqueue_submission
from .forms import ReadingReferenceForm
from .services import assign_to_class
from .video import youtube_embed


class ReadingReferenceTests(IntegratedFixture):
    def test_safe_video_urls_and_no_external_embed_or_invalid_port(self):
        for url in ['https://youtu.be/abcdefghijk','https://www.youtube.com/watch?v=abcdefghijk&t=3',
                    'https://youtube.com/shorts/abcdefghijk']:
            self.assertEqual(youtube_embed(url),'https://www.youtube-nocookie.com/embed/abcdefghijk')
        for url in ['javascript:alert(1)','https://youtube.com.evil.test/watch?v=abcdefghijk',
                    'https://youtube.com:bad/watch?v=abcdefghijk','https://user:pass@youtube.com/watch?v=abcdefghijk',
                    'http://youtu.be/abcdefghijk','https://youtu.be/not-a-valid-video-id']:
            with self.assertRaises(ValidationError):youtube_embed(url)

    def test_form_requires_literal_reference_and_valid_video(self):
        for data in [{'youtube_url':self.speaking.youtube_url,'reference_transcript':'   '},
                {'youtube_url':'https://example.com/video','reference_transcript':'Read along.'},
                {'youtube_url':self.speaking.youtube_url,'reference_transcript':'word '*1501}]:
            self.assertFalse(ReadingReferenceForm(data).is_valid())
        self.speaking.reference_transcript='';self.speaking.save()
        # A legacy SpeakingTask or instruction is not silently treated as an answer.
        with self.assertRaises(ValidationError):
            assign_to_class(actor=self.other_teacher,lesson=self.speaking,classroom=self.other_classroom,
                assigned_at=self.now,due_at=self.now+timedelta(days=1))

    def test_only_management_or_current_class_teacher_can_update_reference(self):
        url=reverse('assignments:reading_reference',args=[self.assignments['speaking'].pk])
        body={'youtube_url':self.speaking.youtube_url,'reference_transcript':'A new literal script.'}
        for user,status in [(self.student,403),(self.other_teacher,404),(self.teacher,302),(self.manager,302),(self.admin,302)]:
            self.client.force_login(user)
            self.assertEqual(self.client.post(url,body).status_code,status)

    def test_reference_update_changes_future_submissions_but_keeps_job_snapshots(self):
        old,_=enqueue_submission(task=self.task,submission_key='old',audio=self.audio())
        self.client.force_login(self.teacher)
        url=reverse('assignments:reading_reference',args=[self.assignments['speaking'].pk])
        self.assertEqual(self.client.post(url,{'youtube_url':self.speaking.youtube_url,
            'reference_transcript':'This is a different video script.'}).status_code,302)
        new,_=enqueue_submission(task=self.task,submission_key='new',audio=self.audio())
        old.refresh_from_db()
        self.assertEqual(old.rubric_snapshot['reference_transcript'],'My hobby is reading.')
        self.assertEqual(new.rubric_snapshot['reference_transcript'],'This is a different video script.')
        self.assertEqual(GradingJob.objects.count(),2)

from django.urls import reverse
from dashboard.testutils import IntegratedFixture


class RecordingFormTests(IntegratedFixture):
    def test_readalong_page_has_mic_without_reference_or_typed_or_file_fallback(self):
        self.client.force_login(self.student)
        response=self.client.get(reverse('submissions:do_task',args=[self.task.pk]))
        for text in ['id="recordStart"','id="recordStop"','id="recordPreview"',
                     'https://www.youtube-nocookie.com/embed/abcdefghijk',
                     'submissions/submit.js']:
            self.assertContains(response,text)
        for text in ['My hobby is reading.','Lời mẫu cần đọc','name="text"','name="audio"','type="file"']:
            self.assertNotContains(response,text)

    def test_legacy_assignment_waits_for_teacher_reference(self):
        assignment=self.assignments['speaking'];assignment.rubric={'skill':'speaking'};assignment.save()
        self.client.force_login(self.student)
        response=self.client.get(reverse('submissions:do_task',args=[self.task.pk]))
        self.assertContains(response,'liên hệ giáo viên')
        self.assertContains(response,'disabled')
        self.assertNotContains(response,'id="recordStart"')

    def test_speaking_does_not_accept_typed_drafts(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.post(reverse('submissions:autosave',args=[self.task.pk]),
            {'text':'My hobby is reading.'},content_type='application/json').status_code,400)

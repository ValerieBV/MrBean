from datetime import timedelta
from django.conf import settings
from django.db import models
from django.utils import timezone


class GradingJob(models.Model):
    class Status(models.TextChoices):
        QUEUED = 'queued', 'Chờ AI'
        PROCESSING = 'processing', 'AI đang chấm'
        AI_REVIEWED = 'ai_reviewed', 'AI đã nhận xét'
        MANUAL = 'manual', 'Chờ giáo viên'
        GRADED = 'graded', 'Đã có điểm chính thức'

    task = models.ForeignKey('dashboard.LearningTask', on_delete=models.PROTECT, related_name='jobs')
    submission_key = models.CharField(max_length=128, unique=True)
    kind = models.CharField(max_length=16, choices=[('speaking', 'Bài nói'), ('vocabulary', 'Từ vựng'), ('listening', 'Nghe')])
    rubric_snapshot = models.JSONField(default=dict, blank=True)
    answers = models.JSONField(default=dict, blank=True)
    transcript = models.TextField(blank=True)
    grading_method = models.CharField(max_length=20, blank=True)
    progress = models.ForeignKey('submissions.LessonProgress', on_delete=models.SET_NULL, null=True, blank=True, related_name='grading_jobs')
    text = models.TextField(blank=True)
    audio = models.FileField(upload_to='ai_submissions/%Y/%m/', blank=True)
    reference_text = models.TextField(blank=True)
    submitted_at = models.DateTimeField(default=timezone.now, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED, db_index=True)
    result = models.JSONField(default=dict, blank=True)
    suggested_score = models.FloatField(null=True, blank=True)
    final_score = models.FloatField(null=True, blank=True)
    teacher_feedback = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    fallback_reason = models.CharField(max_length=64, blank=True)

    @property
    def ai_deadline(self):
        return self.submitted_at + timedelta(seconds=settings.AI_DEADLINE_SECONDS)

    @property
    def sla_deadline(self):
        return self.submitted_at + timedelta(hours=48)

    class Meta:
        ordering = ['submitted_at', 'pk']


class VocabularyPage(models.Model):
    job = models.ForeignKey(GradingJob, on_delete=models.CASCADE, related_name='pages')
    image = models.FileField(upload_to='ai_submissions/vocabulary/%Y/%m/')

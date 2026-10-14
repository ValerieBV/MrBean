from django.conf import settings
from django.db import models
from django.utils import timezone

from assignments.models import Lesson, ListeningQuestion, SpeakingTask


class LessonProgress(models.Model):
    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "Đang làm"
        COMPLETED = "completed", "Hoàn thành"

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lesson_progress"
    )
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="progress")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.IN_PROGRESS)
    score = models.FloatField("Điểm (bài có đáp án)", null=True, blank=True)
    draft = models.JSONField("Bản nháp tự lưu", default=dict, blank=True)
    draft_saved_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("student", "lesson")
        verbose_name = "Tiến độ buổi học"
        verbose_name_plural = "Tiến độ học viên"

    def __str__(self):
        return f"{self.student} - {self.lesson} ({self.get_status_display()})"

    @property
    def is_completed(self):
        return self.status == self.Status.COMPLETED

    @property
    def draft_valid(self):
        if not self.draft or not self.draft_saved_at:
            return False
        return timezone.now() - self.draft_saved_at <= timezone.timedelta(hours=24)


class QuestionResponse(models.Model):
    progress = models.ForeignKey(
        LessonProgress, on_delete=models.CASCADE, related_name="responses"
    )
    question = models.ForeignKey(ListeningQuestion, on_delete=models.CASCADE)
    chosen_option = models.CharField(max_length=1, blank=True)
    filled_text = models.CharField(max_length=255, blank=True)
    is_correct = models.BooleanField(null=True, blank=True)

    class Meta:
        unique_together = ("progress", "question")


class SpeakingRecording(models.Model):
    progress = models.ForeignKey(
        LessonProgress, on_delete=models.CASCADE, related_name="recordings"
    )
    task = models.ForeignKey(SpeakingTask, on_delete=models.CASCADE)
    audio = models.FileField(upload_to="submissions/recordings/")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("progress", "task")

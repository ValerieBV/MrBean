from django.conf import settings
from django.db import models


class Skill(models.TextChoices):
    LISTENING = "listening", "Listening"
    SPEAKING = "speaking", "Speaking"
    VOCABULARY = "vocabulary", "Vocabulary"


class Program(models.TextChoices):
    CHUNG = "CHUNG", "Dùng chung"
    TOEIC = "TOEIC", "TOEIC"
    B1 = "B1", "B1"
    B2 = "B2", "B2"
    VSTEP = "VSTEP", "VSTEP"


class ListeningType(models.TextChoices):
    PART12 = "part12", "Nghe chọn đáp án (ABCD, có hình ảnh)"
    PART34 = "part34", "Nghe điền đáp án"


class Lesson(models.Model):
    skill = models.CharField("Kỹ năng", max_length=20, choices=Skill.choices)
    program = models.CharField(
        "Chương trình", max_length=10, choices=Program.choices, default=Program.CHUNG
    )
    order = models.PositiveIntegerField("Buổi số", default=1)
    title = models.CharField("Tên buổi", max_length=200)
    description = models.TextField("Mô tả", blank=True)
    listening_type = models.CharField(
        "Loại bài nghe", max_length=10, choices=ListeningType.choices, blank=True
    )
    audio_file = models.FileField(
        "File nghe", upload_to="assignments/audio/", blank=True, null=True
    )
    reference_transcript = models.TextField('Lời mẫu chính xác của video', blank=True, help_text='Nội dung học viên phải đọc lại, không phải câu lệnh giao bài.')
    youtube_url = models.URLField("Link YouTube (bài nói)", blank=True)
    is_active = models.BooleanField("Đang mở", default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="created_lessons",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["skill", "program", "order"]
        unique_together = ("skill", "program", "order")
        verbose_name = "Buổi học"
        verbose_name_plural = "Ngân hàng bài tập (Buổi)"

    def __str__(self):
        return f"[{self.get_skill_display()}] Buổi {self.order} - {self.title}"

    @property
    def item_count(self):
        if self.skill == Skill.VOCABULARY:
            return self.words.count()
        if self.skill == Skill.LISTENING:
            return self.questions.count()
        return self.speaking_tasks.count()


class VocabWord(models.Model):
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="words")
    word = models.CharField("Từ", max_length=120)
    word_type = models.CharField("Loại từ", max_length=60, blank=True)
    meaning = models.CharField("Nghĩa", max_length=255)
    example = models.TextField("Ví dụ", blank=True)
    order = models.PositiveIntegerField("Thứ tự", default=1)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.word


class ListeningQuestion(models.Model):
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="questions")
    order = models.PositiveIntegerField("Câu số", default=1)
    image = models.ImageField(
        "Hình ảnh (part 1-2)", upload_to="assignments/listening_img/", blank=True, null=True
    )
    question_text = models.TextField("Nội dung câu hỏi", blank=True)
    option_a = models.CharField("Đáp án A", max_length=255, blank=True)
    option_b = models.CharField("Đáp án B", max_length=255, blank=True)
    option_c = models.CharField("Đáp án C", max_length=255, blank=True)
    option_d = models.CharField("Đáp án D", max_length=255, blank=True)
    correct_option = models.CharField(
        "Đáp án đúng", max_length=1, blank=True,
        choices=[("A", "A"), ("B", "B"), ("C", "C"), ("D", "D")],
    )
    correct_answer = models.CharField("Đáp án điền (tham khảo)", max_length=255, blank=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"Câu {self.order} - {self.lesson.title}"


class SpeakingTask(models.Model):
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="speaking_tasks")
    order = models.PositiveIntegerField("Câu số", default=1)
    sentence = models.TextField("Câu/đoạn cần nói")

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"Câu {self.order} - {self.lesson.title}"


class ClassAssignment(models.Model):
    """A real lesson assigned to one class. Roster lives in LearningTask."""
    lesson = models.ForeignKey(Lesson, on_delete=models.PROTECT, related_name='class_assignments')
    classroom = models.ForeignKey('courses.ClassRoom', on_delete=models.PROTECT, related_name='assignments')
    assigned_at = models.DateTimeField()
    due_at = models.DateTimeField()
    rubric = models.JSONField(default=dict, blank=True)
    vocab_repetitions = models.PositiveSmallIntegerField(default=1)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['lesson', 'classroom'], name='unique_lesson_class')]
        ordering = ['-assigned_at', '-pk']

    def __str__(self):
        return f'{self.classroom.class_code} / {self.lesson.title}'

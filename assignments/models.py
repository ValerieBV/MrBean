from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from .listening import FIRST_NUMBER, LISTENING_SPECS, validate_listening_audio, validate_listening_pdf


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
    video_file = models.FileField('Video mẫu MP4 hoặc WebM', upload_to='assignments/video/', blank=True)
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
    meaning = models.CharField("Nghĩa", max_length=255, blank=True)
    example = models.TextField("Ví dụ", blank=True)
    order = models.PositiveIntegerField("Thứ tự", default=1)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.word


class ListeningExercise(models.Model):
    class Kind(models.TextChoices):
        PART1 = 'part1', 'Dạng 1 · Mô tả tranh'
        PART2 = 'part2', 'Dạng 2 · Hỏi - Đáp'
        PART3 = 'part3', 'Dạng 3 · Cuộc hội thoại ngắn'
        PART4 = 'part4', 'Dạng 4 · Bài nói ngắn'
        LEGACY = 'legacy', 'Bài nghe đã có'

    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='listening_exercises')
    order = models.PositiveSmallIntegerField('Thứ tự bài trong buổi', validators=[MinValueValidator(1), MaxValueValidator(4)])
    kind = models.CharField('Dạng bài', max_length=12, choices=Kind.choices)
    title = models.CharField('Tên bài nghe', max_length=200, blank=True)
    audio_file = models.FileField('File nghe', upload_to='assignments/listening/audio/', blank=True, validators=[validate_listening_audio])
    document_file = models.FileField('Đề bài PDF xem trên web', upload_to='assignments/listening/documents/', blank=True, validators=[validate_listening_pdf])
    question_count = models.PositiveSmallIntegerField('Số câu', validators=[MinValueValidator(1), MaxValueValidator(200)])
    solutions = models.JSONField('Đáp án và giải thích', default=dict, blank=True)

    class Meta:
        ordering = ['order', 'pk']
        constraints = [models.UniqueConstraint(fields=['lesson', 'order'], name='unique_listening_exercise_order')]

    @property
    def choice_letters(self):
        return LISTENING_SPECS[self.kind]['choices']

    @property
    def display_title(self):
        return self.title or LISTENING_SPECS[self.kind]['label']

    def clean(self):
        super().clean()
        if self.lesson_id and self.lesson.skill != Skill.LISTENING:
            raise ValidationError('Chỉ thêm bài nghe vào buổi Listening.')
        expected = LISTENING_SPECS.get(self.kind, {}).get('count')
        if expected is not None and self.question_count != expected:
            raise ValidationError({'question_count': f'Dạng này cần đúng {expected} câu.'})

    def __str__(self):
        return f'Bài {self.order}: {self.display_title}'


class ListeningQuestion(models.Model):
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="questions")
    exercise = models.ForeignKey(ListeningExercise, on_delete=models.CASCADE, related_name='questions', null=True, blank=True)
    order = models.PositiveIntegerField("Câu số", default=1)
    source_number = models.PositiveIntegerField('Số câu trên đề gốc', null=True, blank=True)
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

    @property
    def display_number(self):
        start = FIRST_NUMBER.get(self.exercise.kind, 1) if self.exercise_id else 1
        return self.source_number or start + self.order - 1

    def __str__(self):
        return f"Câu {self.display_number} - {self.lesson.title}"

    def clean(self):
        super().clean()
        if self.exercise_id and self.exercise.lesson_id != self.lesson_id:
            raise ValidationError('Câu hỏi phải thuộc cùng buổi với bài nghe.')
        if self.exercise_id and self.correct_option and self.correct_option not in self.exercise.choice_letters:
            raise ValidationError({'correct_option': 'Đáp án không phù hợp dạng bài nghe.'})


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
    is_active = models.BooleanField('Đang nhận bài', default=True)
    allow_late_submission = models.BooleanField('Cho phép nộp quá hạn', default=True)
    requires_previous = models.BooleanField('Hoàn thành bài trước để mở bài này', default=True)
    reference_video = models.FileField(upload_to='assignments/video/', blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['lesson', 'classroom'], name='unique_lesson_class')]
        ordering = ['-assigned_at', '-pk']

    def __str__(self):
        return f'{self.classroom.class_code} / {self.lesson.title}'

    @property
    def reference_version(self):
        import hashlib
        import json
        content = json.dumps({'rubric': self.rubric, 'video': self.reference_video.name}, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(content.encode()).hexdigest()

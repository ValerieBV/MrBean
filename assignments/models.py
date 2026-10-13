
from django.db import models
from django.conf import settings
class assignment(models.Model):

    # Chương trình / trình độ luyện đề
    PROGRAM_CHOICES = [
        ("TOEIC", "TOEIC"),
        ("B1", "B1"),
        ("B2", "B2"),
        ("VSTEP", "VSTEP"),
    ]

    # Loại bài tập
    CATEGORY_CHOICES = [
        ("listening", "Bài tập Nghe"),
        ("speaking", "Bài tập Nói"),
        ("vocabulary", "Bài tập Từ vựng"),
        ("practice_test", "Kho luyện đề"),
    ]

    # Mã bài tập
    code = models.CharField(
        max_length=30,
        unique=True,
        verbose_name="Mã bài tập",
    )

    # Tên bài tập
    title = models.CharField(
        max_length=255,
        verbose_name="Tên bài tập",
    )

    # Chỉ chọn chương trình khi là bài luyện đề
    program = models.CharField(
        max_length=10,
        choices=PROGRAM_CHOICES,
        blank=True,
        default="",
        verbose_name="Chương trình luyện đề",
    )

    # Danh mục bài tập
    category = models.CharField(
        max_length=30,
        choices=CATEGORY_CHOICES,
        verbose_name="Danh mục bài tập",
    )

    # Mô tả
    description = models.TextField(
        blank=True,
        verbose_name="Mô tả",
    )

    # Nội dung bài tập
    content = models.TextField(
        blank=True,
        verbose_name="Nội dung bài tập",
    )

    # File âm thanh
    audio_file = models.FileField(
        upload_to="assignments/audio/",
        blank=True,
        null=True,
        verbose_name="File âm thanh",
    )

    # Tài liệu đính kèm
    attachment = models.FileField(
        upload_to="assignments/files/",
        blank=True,
        null=True,
        verbose_name="Tài liệu đính kèm",
    )

    # Đáp án
    answer_key = models.TextField(
        blank=True,
        verbose_name="Đáp án",
    )

    # Người tạo bài tập
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_assignments",
        verbose_name="Người tạo",
    )

    # Trạng thái sử dụng
    is_active = models.BooleanField(
        default=True,
        verbose_name="Đang sử dụng",
    )

    # Thời gian tạo
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Ngày tạo",
    )

    # Thời gian cập nhật
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Ngày cập nhật",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Bài tập"
        verbose_name_plural = "Ngân hàng bài tập"

    def __str__(self):
        return f"{self.code} - {self.title}"

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.urls import reverse


class Conversation(models.Model):
    KNOWLEDGE, CONTACT = 'knowledge', 'contact'
    AI, WAITING, ANSWERED, CLOSED = 'ai', 'waiting', 'answered', 'closed'
    KIND_CHOICES = [(KNOWLEDGE, 'Hỏi đáp kiến thức'), (CONTACT, 'Liên hệ và phản ánh')]
    STATUS_CHOICES = [(AI, 'Đang hỏi AI'), (WAITING, 'Chờ phản hồi'),
                      (ANSWERED, 'Đã được phản hồi'), (CLOSED, 'Đã kết thúc')]
    CATEGORY_CHOICES = [('knowledge', 'Giải thích kiến thức'), ('grade', 'Thắc mắc về kết quả'),
                        ('technical', 'Lỗi kỹ thuật'), ('schedule', 'Lịch học và bài tập'), ('other', 'Phản ánh khác')]
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='support_conversations')
    kind = models.CharField(max_length=12, choices=KIND_CHOICES)
    subject = models.CharField(max_length=180)
    creation_key = models.UUIDField(null=True, blank=True, unique=True)
    category = models.CharField(max_length=16, choices=CATEGORY_CHOICES, default='knowledge')
    job = models.ForeignKey('ai_core.GradingJob', null=True, blank=True, on_delete=models.PROTECT, related_name='conversations')
    classroom = models.ForeignKey('courses.ClassRoom', null=True, blank=True, on_delete=models.PROTECT, related_name='support_conversations')
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                                  related_name='support_inbox')
    recipient_role = models.CharField(max_length=12, choices=[('teacher', 'Giáo viên phụ trách'), ('management', 'Quản lý')], blank=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=AI)
    escalated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-updated_at', '-pk']
        constraints = [models.UniqueConstraint(fields=['student', 'job'], condition=Q(kind='knowledge'),
                                                name='one_study_thread_per_result')]

    def get_absolute_url(self):
        return reverse('support:detail', args=[self.pk])


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT)
    role = models.CharField(max_length=12, choices=[('student', 'Học viên'), ('assistant', 'AI trợ giảng'),
                                                  ('staff', 'Giáo viên / Quản lý'), ('system', 'Hệ thống')])
    body = models.TextField(max_length=6000)
    client_key = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'pk']
        constraints = [models.UniqueConstraint(fields=['conversation', 'client_key'], name='unique_support_message_request')]


class TutorAttempt(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='ai_attempts')
    question = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='ai_attempts')
    answer = models.OneToOneField(Message, null=True, blank=True, on_delete=models.SET_NULL, related_name='tutor_attempt')
    status = models.CharField(max_length=12, choices=[('processing', 'Đang xử lý'), ('completed', 'Hoàn tất'),
                                                   ('failed', 'Chưa trả lời được'), ('cancelled', 'Đã dừng')])
    route = models.CharField(max_length=12, blank=True)
    error_code = models.CharField(max_length=32, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        constraints = [models.UniqueConstraint(fields=['conversation'], condition=Q(status='processing'),
                                                name='one_active_tutor_request_per_thread')]

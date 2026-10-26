import uuid
from django import forms
from django.db.models import Q
from django.utils import timezone
from accounts.models import CustomUser
from ai_core.models import GradingJob
from courses.models import ClassRoom
from .models import Conversation


class MessageForm(forms.Form):
    body = forms.CharField(label='Nội dung', min_length=3, max_length=4000,
                           widget=forms.Textarea(attrs={'rows':4, 'maxlength':4000}))
    client_key = forms.UUIDField(widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.initial.setdefault('client_key', uuid.uuid4())

    def clean(self):
        data=super().clean()
        if not data.get('client_key'):
            self.add_error(None,'Biểu mẫu chưa hợp lệ. Vui lòng tải lại trang trước khi gửi.')
        return data


class ContactForm(MessageForm):
    subject = forms.CharField(label='Tiêu đề', min_length=3, max_length=180)
    category = forms.ChoiceField(label='Nội dung cần liên hệ', choices=[c for c in Conversation.CATEGORY_CHOICES if c[0]!='knowledge'])
    target = forms.ChoiceField(label='Gửi đến')
    job = forms.ModelChoiceField(label='Kết quả liên quan (nếu có)', required=False, queryset=GradingJob.objects.none())

    def __init__(self, *args, student, **kwargs):
        super().__init__(*args, **kwargs)
        classes = ClassRoom.objects.filter(enrollments__student=student, teacher__is_active=True,
                                            teacher__role='teacher').select_related('teacher').distinct().order_by('class_code')
        choices = [('', 'Chọn giáo viên hoặc quản lý')]
        choices += [(f'teacher:{c.pk}', f'Giáo viên lớp {c.class_code} — {c.teacher.display_name}') for c in classes]
        choices += [(f'management:{u.pk}', f'{u.get_role_display()} — {u.display_name}') for u in
                    CustomUser.objects.filter(Q(role__in=['admin','manager'])|Q(is_superuser=True), is_active=True).order_by('username')]
        self.fields['target'].choices = choices
        self.fields['job'].queryset = GradingJob.objects.filter(task__learner=student, status='graded').select_related('task').order_by('-submitted_at')
        self.fields['job'].label_from_instance = lambda j: f'{j.task.title} · {timezone.localtime(j.submitted_at):%d/%m/%Y}'
        self.order_fields(['subject','category','target','job','body','client_key'])

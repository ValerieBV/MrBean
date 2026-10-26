from django import forms

from .models import Lesson, VocabWord, ListeningQuestion, SpeakingTask

INPUT = "w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-500 text-sm"


class LessonForm(forms.ModelForm):
    class Meta:
        model = Lesson
        fields = ["skill", "program", "order", "title", "description",
                  "listening_type", "audio_file", "video_file", "youtube_url", "reference_transcript", "is_active"]
        widgets = {
            "skill": forms.Select(attrs={"class": INPUT, "id": "id_skill"}),
            "program": forms.Select(attrs={"class": INPUT}),
            "order": forms.NumberInput(attrs={"class": INPUT}),
            "title": forms.TextInput(attrs={"class": INPUT}),
            "description": forms.Textarea(attrs={"class": INPUT, "rows": 2}),
            "listening_type": forms.Select(attrs={"class": INPUT}),
            "audio_file": forms.ClearableFileInput(attrs={"class": INPUT}),
            "reference_transcript": forms.Textarea(attrs={'rows':6, 'maxlength':20000}),
            "youtube_url": forms.URLInput(attrs={"class": INPUT, "placeholder": "https://youtube.com/..."}),
        }

    def clean_skill(self):
        value = self.cleaned_data['skill']
        if self.instance.pk and value != self.instance.skill and self.instance.item_count:
            raise forms.ValidationError('Buổi đã có nội dung. Giữ kỹ năng hiện tại hoặc tạo buổi mới để đổi kỹ năng.')
        return value

    def clean_video_file(self):
        video = self.cleaned_data.get('video_file')
        from django.core.files.uploadedfile import UploadedFile
        if isinstance(video, UploadedFile):
            from django.core.exceptions import ValidationError
            from pathlib import Path
            if not 0 < video.size <= 50*1024*1024 or Path(video.name).suffix.lower() not in ('.mp4','.webm'):
                raise ValidationError('Video cần là MP4/WebM, tối đa 50 MiB.')
        return video

    def clean_audio_file(self):
        from django.core.files.uploadedfile import UploadedFile
        from pathlib import Path
        audio = self.cleaned_data.get('audio_file')
        if isinstance(audio, UploadedFile) and (not 0 < audio.size <= 20*1024*1024 or Path(audio.name).suffix.lower() not in ('.mp3','.wav','.m4a','.mp4','.ogg','.webm')):
            raise forms.ValidationError('File nghe cần là MP3/WAV/M4A/MP4/OGG/WebM, tối đa 20 MiB.')
        return audio


class VocabWordForm(forms.ModelForm):
    class Meta:
        model = VocabWord
        fields = ["order", "word", "word_type", "meaning", "example"]
        widgets = {f: forms.TextInput(attrs={"class": INPUT}) for f in ["word", "word_type", "meaning"]}
        widgets["order"] = forms.NumberInput(attrs={"class": INPUT})
        widgets["example"] = forms.Textarea(attrs={"class": INPUT, "rows": 2})


class ListeningQuestionForm(forms.ModelForm):
    class Meta:
        model = ListeningQuestion
        fields = ["order", "image", "question_text", "option_a", "option_b",
                  "option_c", "option_d", "correct_option", "correct_answer"]
        widgets = {
            "order": forms.NumberInput(attrs={"class": INPUT}),
            "image": forms.ClearableFileInput(attrs={"class": INPUT}),
            "question_text": forms.Textarea(attrs={"class": INPUT, "rows": 2}),
            "option_a": forms.TextInput(attrs={"class": INPUT}),
            "option_b": forms.TextInput(attrs={"class": INPUT}),
            "option_c": forms.TextInput(attrs={"class": INPUT}),
            "option_d": forms.TextInput(attrs={"class": INPUT}),
            "correct_option": forms.Select(attrs={"class": INPUT}),
            "correct_answer": forms.TextInput(attrs={"class": INPUT}),
        }


class SpeakingTaskForm(forms.ModelForm):
    class Meta:
        model = SpeakingTask
        fields = ["order", "sentence"]
        widgets = {
            "order": forms.NumberInput(attrs={"class": INPUT}),
            "sentence": forms.Textarea(attrs={"class": INPUT, "rows": 2}),
        }


class AssignmentForm(forms.Form):
    lesson = forms.ModelChoiceField(queryset=Lesson.objects.filter(is_active=True), label='Buổi học')
    classroom = forms.ModelChoiceField(queryset=None, label='Lớp nhận bài')
    assigned_at = forms.DateTimeField(label='Thời điểm giao', widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}))
    due_at = forms.DateTimeField(label='Hạn nộp', widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}))
    repetitions = forms.IntegerField(label='Số lượt viết mỗi từ (chỉ Vocabulary)', min_value=1, max_value=100, initial=1)
    allow_late_submission = forms.BooleanField(label='Cho phép nộp quá hạn', required=False, initial=True)
    requires_previous = forms.BooleanField(label='Yêu cầu hoàn thành bài trước cùng kỹ năng', required=False, initial=True)

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        from ai_core.permissions import classes_for
        self.fields['classroom'].queryset = classes_for(user).filter(is_active=True)


class ReadingReferenceForm(forms.Form):
    youtube_url = forms.URLField(label='Video mẫu YouTube HTTPS', required=False)
    video_file = forms.FileField(label='Hoặc tải video MP4/WebM mới', required=False)
    reference_transcript = forms.CharField(label='Lời mẫu chính xác của đoạn cần đọc', max_length=20000,
        widget=forms.Textarea(attrs={'rows':8}), help_text='Không nhập yêu cầu kiểu Introduce yourself. Nhập nguyên văn lời cần đọc.')

    def __init__(self,*args,assignment=None,**kwargs):
        super().__init__(*args,**kwargs)
        self.assignment=assignment

    clean_video_file = LessonForm.clean_video_file

    def clean(self):
        data=super().clean()
        if data.get('youtube_url'):
            from .video import youtube_embed
            data['video_embed_url']=youtube_embed(data['youtube_url'])
        elif not data.get('video_file') and not (self.assignment and self.assignment.reference_video):
            self.add_error('youtube_url','Cần video tải lên hoặc liên kết YouTube.')
        if data.get('reference_transcript'):
            from ai_core.reading import words, MAX_REFERENCE_WORDS
            count=len(words(data['reference_transcript']))
            if not 1 <= count <= MAX_REFERENCE_WORDS:
                self.add_error('reference_transcript','Lời mẫu phải có từ 1 đến 1500 từ.')
        return data


class AssignmentUpdateForm(forms.ModelForm):
    class Meta:
        from .models import ClassAssignment
        model = ClassAssignment
        fields = ['due_at','is_active','allow_late_submission','requires_previous']
        labels = {'due_at':'Hạn nộp'}
        widgets = {'due_at':forms.DateTimeInput(attrs={'type':'datetime-local'},format='%Y-%m-%dT%H:%M')}

    def clean_due_at(self):
        value=self.cleaned_data['due_at']
        if value < self.instance.assigned_at:
            raise forms.ValidationError('Hạn nộp không thể trước thời điểm giao.')
        return value

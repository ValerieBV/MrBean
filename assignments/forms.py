from django import forms
import json

from .models import Lesson, VocabWord, ListeningQuestion, SpeakingTask, ListeningExercise

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
        labels = {'meaning': 'Nghĩa (không bắt buộc)'}
        widgets = {f: forms.TextInput(attrs={"class": INPUT}) for f in ["word", "word_type", "meaning"]}
        widgets["order"] = forms.NumberInput(attrs={"class": INPUT})
        widgets["example"] = forms.Textarea(attrs={"class": INPUT, "rows": 2})


class VocabularyImportForm(forms.Form):
    text = forms.CharField(label='Dán danh sách từ', required=False, max_length=250000, strip=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 9,
            'placeholder': 'department\nissue\ncorporate\nsign up', 'spellcheck': 'false'}))
    upload = forms.FileField(label='Hoặc tải tệp CSV / TXT', required=False,
        widget=forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': '.csv,.txt'}))

    def clean(self):
        from pathlib import Path
        from .vocabulary_import import parse_vocabulary_text

        data = super().clean()
        text, upload = data.get('text', ''), data.get('upload')
        if self.errors:
            return data
        if bool(text.strip()) == bool(upload):
            raise forms.ValidationError('Chọn một cách nhập: dán danh sách hoặc tải một tệp CSV/TXT.')
        csv_file = False
        if upload:
            suffix = Path(upload.name).suffix.lower()
            if suffix not in ('.csv', '.txt') or not 0 < upload.size <= 1024 * 1024:
                raise forms.ValidationError('Chỉ nhận tệp CSV/TXT, tối đa 1 MiB.')
            try:
                text = upload.read(1024 * 1024 + 1).decode('utf-8-sig')
            except UnicodeDecodeError as exc:
                raise forms.ValidationError('Tệp cần mã hóa UTF-8. Lưu lại bằng CSV UTF-8 hoặc dán trực tiếp từ Excel.') from exc
            csv_file = suffix == '.csv'
        data['rows'] = parse_vocabulary_text(text, csv_file=csv_file)
        return data


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.exercise_id:
            self.fields['correct_option'].choices = [('', '---------')] + [
                (c, c) for c in self.instance.exercise.choice_letters]
            if self.instance.exercise.kind == 'part2':
                self.fields['option_d'].widget = forms.HiddenInput()

    def clean(self):
        data = super().clean()
        if self.instance.pk and self.instance.exercise_id and self.instance.exercise.kind == 'part2':
            data['option_d'] = ''
        return data


class ListeningExerciseForm(forms.ModelForm):
    question_data = forms.CharField(required=False, max_length=250000, widget=forms.HiddenInput(), label='Nội dung câu hỏi')
    answer_key = forms.CharField(label='Dán đáp án hàng loạt', required=False,
        widget=forms.Textarea(attrs={'rows': 7, 'placeholder': '1.A 2.C 3.B 4.D 5.A 6.C', 'class': INPUT}),
        help_text='Nhập số câu kèm đáp án, hoặc dán cả cột đáp án từ Excel. Không cần nhập từng câu.')
    answer_key_file = forms.FileField(label='Hoặc tải bảng đáp án CSV / TXT', required=False,
        widget=forms.ClearableFileInput(attrs={'accept': '.csv,.txt', 'class': INPUT}),
        help_text='CSV UTF-8: number,answer. Có thể thêm question_text,A,B,C,D để nhập cả nội dung.')

    class Meta:
        model = ListeningExercise
        fields = ['order', 'kind', 'title', 'audio_file', 'document_file', 'question_count']
        widgets = {
            'order': forms.NumberInput(attrs={'min': 1, 'max': 4, 'class': INPUT}),
            'kind': forms.Select(attrs={'class': INPUT}),
            'title': forms.TextInput(attrs={'class': INPUT}),
            'audio_file': forms.ClearableFileInput(attrs={'accept': 'audio/*,.mp4,.webm', 'class': INPUT}),
            'document_file': forms.ClearableFileInput(attrs={'accept': 'application/pdf,.pdf', 'class': INPUT}),
            'question_count': forms.NumberInput(attrs={'min': 1, 'max': 200, 'class': INPUT}),
        }

    def __init__(self, *args, lesson, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.lesson = lesson
        self.fields['kind'].choices = [(k, v) for k, v in ListeningExercise.Kind.choices
            if k != 'legacy' or self.instance.pk and self.instance.kind == 'legacy']
        self.fields['question_count'].required = False
        self.fields['question_count'].help_text = 'Số câu cố định theo dạng bài: 6 / 25 / 39 / 30.'
        self.fields['audio_file'].help_text = 'Tải file nghe đầy đủ cho bài này, tối đa 50 MiB.'
        self.fields['document_file'].help_text = 'Dạng 1 bắt buộc PDF đề bài; dạng 3/4 có thể thêm PDF. Dạng 2 chỉ dùng file nghe. Không đưa đáp án vào PDF học viên xem.'
        if self.instance.pk:
            questions = list(self.instance.questions.all())
            self.initial['answer_key'] = '\n'.join(f'{q.display_number}.{q.correct_option}' for q in questions)
            self.initial['question_data'] = json.dumps([{'number':q.display_number,
                **{key:getattr(q,key) for key in ['question_text','option_a','option_b','option_c','option_d']}}
                for q in questions], ensure_ascii=False)

    def clean(self):
        from .listening import LISTENING_SPECS, parse_answer_key
        data = super().clean()
        spec = LISTENING_SPECS.get(data.get('kind'))
        if not spec:
            return data
        if spec['count'] is not None:
            if data.get('question_count') not in (None, spec['count']):
                self.add_error('question_count', f'Dạng này cần đúng {spec["count"]} câu.')
            data['question_count'] = spec['count']
        elif not data.get('question_count'):
            self.add_error('question_count', 'Nhập số câu của bài này.')
        if not data.get('audio_file'):
            self.add_error('audio_file', 'Cần tải file nghe cho bài này.')
        if data.get('kind') == 'part1' and not data.get('document_file'):
            self.add_error('document_file', 'Dạng Mô tả tranh cần PDF để học viên xem trên web.')
        text = data.get('answer_key', '')
        upload = data.get('answer_key_file')
        if upload:
            if upload.size > 1024 * 1024 or not upload.name.lower().endswith(('.csv', '.txt')):
                self.add_error('answer_key_file', 'Chỉ nhận CSV/TXT tối đa 1 MiB.')
                return data
            try:
                text = upload.read().decode('utf-8-sig')
            except UnicodeDecodeError:
                self.add_error('answer_key_file', 'Lưu bảng đáp án bằng CSV UTF-8.')
                return data
        if data.get('question_count') and 1 <= data['question_count'] <= 200:
            from .question_import import normalize_questions, default_numbers
            try:
                raw_content = data.get('question_data') or (self.initial.get('question_data') if self.instance.pk else '[]')
                content = normalize_questions(json.loads(raw_content))
                if content and len(content) != data['question_count']:
                    raise forms.ValidationError(f'Cần đủ {data["question_count"]} câu hỏi, hiện có {len(content)} câu.')
            except (ValueError, TypeError, forms.ValidationError) as exc:
                self.add_error('question_data', exc if isinstance(exc, forms.ValidationError) else 'Nội dung câu hỏi không hợp lệ.')
                return data
            expected_numbers = default_numbers(data['kind'], data['question_count'])
            if data['kind'] == 'part2':
                content = []
            numbers = [row['number'] for row in content] or expected_numbers
            if data['kind'] == 'part4' and numbers != expected_numbers:
                self.add_error('question_data', 'Dạng 4 sử dụng các câu 71–100. Chọn đúng phần đề và kiểm tra lại số câu.')
                return data
            try:
                rows = parse_answer_key(text, data['question_count'], spec['choices'], numbers)
            except forms.ValidationError as exc:
                self.add_error('answer_key_file' if upload else 'answer_key', exc)
                return data
            problems = []
            for index, row in enumerate(rows):
                source = content[index] if content else {}
                row['source_number'] = source.get('number') or row.get('source_number') or numbers[index]
                for key in ['question_text','option_a','option_b','option_c','option_d']:
                    if source.get(key):
                        row[key] = source[key]
                if data['kind'] == 'part2':
                    row['question_text'] = ''
                    for letter in 'ABCD':
                        row['option_'+letter.lower()] = letter if letter in spec['choices'] else ''
                if source.get('uncertain'):
                    problems.append(f'Câu {row["source_number"]}: kiểm tra phần nhận dạng chưa rõ trước khi lưu.')
                if data['kind'] in ('part3','part4'):
                    if not row.get('question_text', '').strip():
                        problems.append(f'Câu {row["source_number"]}: chưa có nội dung câu hỏi.')
                    missing = [c for c in spec['choices'] if row.get('option_'+c.lower(), '').strip() in ('', c)]
                    if missing:
                        problems.append(f'Câu {row["source_number"]}: cần nội dung lựa chọn {" / ".join(missing)}.')
            if problems:
                self.add_error('question_data', problems)
            data['answer_rows'] = rows
        return data

    def clean_audio_file(self):
        from .listening import validate_listening_audio
        value = self.cleaned_data.get('audio_file')
        validate_listening_audio(value)
        return value

    def clean_document_file(self):
        if self.cleaned_data.get('kind') == 'part2':
            return False
        from .listening import validate_listening_pdf
        value = self.cleaned_data.get('document_file')
        validate_listening_pdf(value)
        return value


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
    assigned_at = forms.DateTimeField(label='Thời điểm mở bài', widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
        help_text='Giờ Việt Nam (UTC+7). Học viên thấy bài từ thời điểm này.')
    due_at = forms.DateTimeField(label='Hạn nộp', widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
        help_text='Hạn nộp phải bằng hoặc sau thời điểm mở bài.')
    repetitions = forms.IntegerField(label='Số lượt viết mỗi từ', min_value=1, max_value=100, initial=1, required=False,
        help_text='Áp dụng cho từng từ trong bài Vocabulary, từ 1 đến 100 lượt.')
    allow_late_submission = forms.BooleanField(label='Cho phép nộp quá hạn', required=False, initial=True)
    requires_previous = forms.BooleanField(label='Yêu cầu hoàn thành bài trước cùng kỹ năng', required=False, initial=True)

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        from ai_core.permissions import classes_for
        self.fields['classroom'].queryset = classes_for(user).filter(is_active=True)
        from django.utils import timezone
        self.initial.setdefault('assigned_at', timezone.localtime().replace(second=0, microsecond=0))
        for field in self.fields.values():
            if not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs['class'] = INPUT
        self.fields['allow_late_submission'].help_text = 'Nếu tắt, hệ thống ngừng nhận bài sau hạn nộp.'
        self.fields['requires_previous'].help_text = 'Bài trước cùng kỹ năng, chương trình và lớp phải hoàn thành hoặc được miễn. Chỉ nộp bài chưa đủ để mở bài sau.'

    def clean(self):
        data = super().clean()
        lesson, classroom = data.get('lesson'), data.get('classroom')
        if data.get('assigned_at') and data.get('due_at') and data['due_at'] < data['assigned_at']:
            self.add_error('due_at', 'Hạn nộp không thể trước thời điểm mở bài.')
        if lesson and lesson.skill == 'vocabulary':
            if data.get('repetitions') is None and 'repetitions' not in self.errors:
                self.add_error('repetitions', 'Nhập số lượt viết yêu cầu cho mỗi từ.')
        elif lesson:
            data['repetitions'] = 1
        if classroom and (not classroom.teacher_id or not classroom.teacher.is_active or classroom.teacher.role != 'teacher'):
            self.add_error('classroom', 'Lớp cần có giáo viên đang hoạt động trước khi giao bài.')
        if lesson and classroom:
            from .models import ClassAssignment
            if ClassAssignment.objects.filter(lesson=lesson, classroom=classroom).exists():
                self.add_error(None, 'Buổi học này đã được giao cho lớp. Mở lượt giao hiện có để chỉnh hạn nộp.')
        return data


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

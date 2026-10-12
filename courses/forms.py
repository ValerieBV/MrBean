from django import forms
from courses.models import Course, ClassRoom, Enrollment, ExemptionRequest
from accounts.models import CustomUser


class ClassRoomForm(forms.ModelForm):
    class Meta:
        model = ClassRoom
        fields = ('class_code', 'name', 'course', 'teacher', 'start_date', 'end_date', 'is_active')
        widgets = {
            'class_code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'VD: TOEIC-K24'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'VD: Lớp TOEIC Cấp Tốc Tối 2-4-6'}),
            'course': forms.Select(attrs={'class': 'form-select'}),
            'teacher': forms.Select(attrs={'class': 'form-select'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Chỉ hiển thị người dùng có vai trò là Giáo viên để phân công chấm bài
        self.fields['teacher'].queryset = CustomUser.objects.filter(
            role=CustomUser.ROLE_TEACHER,
            is_active=True
        )
        self.fields['teacher'].empty_label = "-- Chưa phân công giáo viên --"


class AssignTeacherForm(forms.Form):
    teacher = forms.ModelChoiceField(
        queryset=CustomUser.objects.filter(role=CustomUser.ROLE_TEACHER, is_active=True),
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Chọn Giáo viên giảng dạy & chấm bài",
        empty_label="-- Chọn giáo viên --"
    )


class EnrollStudentForm(forms.Form):
    student = forms.ModelChoiceField(
        queryset=CustomUser.objects.filter(role=CustomUser.ROLE_STUDENT, is_active=True),
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Chọn Học viên cần thêm vào lớp",
        empty_label="-- Chọn học viên --"
    )

    def __init__(self, *args, classroom=None, **kwargs):
        super().__init__(*args, **kwargs)
        if classroom:
            # Loại trừ những học viên đã có trong lớp rồi
            enrolled_ids = classroom.enrollments.values_list('student_id', flat=True)
            self.fields['student'].queryset = self.fields['student'].queryset.exclude(id__in=enrolled_ids)


class ExemptionRequestForm(forms.ModelForm):
    """
    Form xin miễn BTVN của học viên:
    Quy tắc nghiệp vụ: CHỈ CHO PHÉP MIỄN BÀI TẬP NGHE (LISTENING).
    """
    class Meta:
        model = ExemptionRequest
        fields = ('homework_type', 'session_title', 'reason')
        widgets = {
            'homework_type': forms.Select(attrs={'class': 'form-select'}),
            'session_title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'VD: Buổi 3 - Listening Part 2'}),
            'reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Nhập lý do xin miễn...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Khóa lựa chọn chỉ cho phép chọn Listening hoặc hiển thị cảnh báo
        self.fields['homework_type'].help_text = "Lưu ý: Trung tâm chỉ áp dụng miễn cho bài tập Nghe (Listening)."

    def clean_homework_type(self):
        hw_type = self.cleaned_data.get('homework_type')
        if hw_type != ExemptionRequest.HOMEWORK_TYPE_LISTENING:
            raise forms.ValidationError("Quy định trung tâm Mr Bean: CHỈ MIỄN BÀI TẬP NGHE (LISTENING)! Bài tập Từ vựng và Nói bắt buộc phải làm.")
        return hw_type


class ExemptionReviewForm(forms.Form):
    action = forms.ChoiceField(
        choices=[('approve', 'Chấp thuận (Duyệt)'), ('reject', 'Từ chối')],
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        label="Quyết định"
    )
    note = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Ghi chú cho học viên hoặc lý do từ chối...'}),
        label="Ghi chú / Lý do"
    )

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

    def clean_teacher(self):
        teacher = self.cleaned_data.get('teacher')
        if self.instance.pk and self.instance.assignments.exists() and not teacher:
            raise forms.ValidationError('Lớp đã có bài tập cần giữ một giáo viên phụ trách chấm và tra cứu.')
        return teacher


class EnrollmentStatusForm(forms.Form):
    status = forms.ChoiceField(label='Trạng thái ghi danh', choices=Enrollment.STATUS_CHOICES)


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
        # Học viên cố định 1 lớp: loại trừ những học viên đã có lớp active
        enrolled_ids = Enrollment.objects.filter(status=Enrollment.STATUS_ACTIVE).values_list('student_id', flat=True)
        self.fields['student'].queryset = self.fields['student'].queryset.exclude(id__in=enrolled_ids)


class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ['code','name','course_type','description']
        widgets = {'description':forms.Textarea(attrs={'rows':3})}


class ExemptionRequestForm(forms.ModelForm):
    assignment = forms.ModelChoiceField(queryset=None, label='Bài tập xin miễn', empty_label='Chọn bài chưa nộp')

    class Meta:
        model = ExemptionRequest
        fields = ['assignment','reason']
        widgets = {'reason':forms.Textarea(attrs={'rows':4,'maxlength':5000})}

    def __init__(self, *args, student=None, classroom=None, **kwargs):
        super().__init__(*args, **kwargs)
        from assignments.models import ClassAssignment
        from django.utils import timezone
        rows = ClassAssignment.objects.none()
        if student and classroom:
            blocked = ExemptionRequest.objects.filter(enrollment__student=student,
                status__in=['pending','approved']).values('assignment_id')
            rows = ClassAssignment.objects.filter(classroom=classroom, is_active=True,
                lesson__skill__in=['speaking','vocabulary'], assigned_at__lte=timezone.now(),
                tasks__learner=student, tasks__jobs__isnull=True, tasks__exemption__isnull=True).exclude(pk__in=blocked).distinct()
        self.fields['assignment'].queryset = rows.select_related('lesson','classroom')
        self.fields['reason'].max_length = 5000


class ExemptionReviewForm(forms.Form):
    action = forms.ChoiceField(label='Quyết định', choices=[('approve','Chấp thuận'),('reject','Từ chối')], widget=forms.RadioSelect)
    note = forms.CharField(label='Ghi chú hoặc lý do từ chối', required=False,
        max_length=5000, widget=forms.Textarea(attrs={'rows':3}))

    def __init__(self, *args, exemption=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.exemption = exemption
        if exemption and not exemption.assignment_id:
            from assignments.models import ClassAssignment
            self.fields['assignment'] = forms.ModelChoiceField(required=False,
                label='Liên kết bài giao cho đơn cũ', queryset=ClassAssignment.objects.filter(
                    classroom=exemption.enrollment.classroom, lesson__skill=exemption.homework_type,
                    tasks__learner=exemption.enrollment.student, tasks__jobs__isnull=True,
                    tasks__exemption__isnull=True, is_active=True).distinct())

    def clean(self):
        data=super().clean()
        if data.get('action')=='reject' and not data.get('note','').strip():
            self.add_error('note','Nhập lý do từ chối để học viên biết cách xử lý.')
        if data.get('action')=='approve' and self.exemption and not self.exemption.assignment_id and not data.get('assignment'):
            self.add_error('assignment','Chọn đúng bài giao trước khi duyệt miễn đơn cũ.')
        return data

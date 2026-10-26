from django import forms
from django.contrib.auth.forms import UserCreationForm
from accounts.models import CustomUser
from django.contrib.auth.password_validation import validate_password
from django.db.models import Q


class CustomUserCreationForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Nhập mật khẩu'}),
        label="Mật khẩu"
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Xác nhận lại mật khẩu'}),
        label="Xác nhận mật khẩu"
    )

    class Meta:
        model = CustomUser
        fields = ('username', 'email', 'first_name', 'last_name', 'role', 'phone_number', 'student_code')
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Tên đăng nhập'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Địa chỉ email'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Họ và tên đệm'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Tên'}),
            'role': forms.Select(attrs={'class': 'form-select'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Số điện thoại'}),
            'student_code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'VD: T253C1KieuAnh01 (T=TOEIC, V=VSTEP, B=B1)'
            }),
        }

    def __init__(self, *args, current_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['student_code'].help_text = (
            "Định dạng: [Chứng chỉ][Khóa][Cơ sở][Tên][STT] (VD: T253C1KieuAnh01). "
            "Ký tự đầu xác định hạn mức: T/V = 8 buổi, B = 5 buổi miễn BTVN (Speaking & Vocab)."
        )
        if current_user and current_user.role == CustomUser.ROLE_MANAGER:
            # Quản lý được phân quyền tạo tài khoản cho Học viên
            self.fields['role'].choices = [
                (CustomUser.ROLE_STUDENT, 'Học viên'),
            ]
            self.fields['role'].initial = CustomUser.ROLE_STUDENT

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        if password and confirm_password and password != confirm_password:
            self.add_error('confirm_password', "Mật khẩu xác nhận không trùng khớp.")
        if password:
            self.instance.username = cleaned_data.get('username', '')
            validate_password(password, self.instance)
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
        return user


class CustomUserUpdateForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = ('email', 'first_name', 'last_name', 'role', 'phone_number', 'student_code', 'is_active')
        widgets = {
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'role': forms.Select(attrs={'class': 'form-select'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
            'student_code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'VD: T253C1KieuAnh01 (T=TOEIC, V=VSTEP, B=B1)'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['student_code'].help_text = (
            "Ký tự đầu xác định hạn mức: T/V = 8 buổi, B = 5 buổi miễn BTVN (Speaking & Vocab)."
        )

    def clean(self):
        data = super().clean()
        user = self.instance
        if data.get('role') != user.role:
            if user.teaching_classes.exists() or user.class_enrollments.exists() or user.learning_tasks.exists():
                self.add_error('role','Tài khoản đã có lớp hoặc lịch sử học tập; giữ vai trò để bảo toàn dữ liệu.')
            if user.is_superuser:
                self.add_error('role','Superuser phải giữ vai trò admin.')
        if not data.get('is_active') and (user.role=='admin' or user.is_superuser):
            if not CustomUser.objects.filter(Q(role='admin')|Q(is_superuser=True), is_active=True).exclude(pk=user.pk).exists():
                self.add_error('is_active','Cần giữ ít nhất một quản trị viên hoạt động.')
        if not data.get('is_active') and user.role=='teacher' and user.teaching_classes.filter(is_active=True).exists():
            self.add_error('is_active','Phân công giáo viên thay thế cho các lớp đang hoạt động trước.')
        code = data.get('student_code') or ''
        maximum = 5 if code.upper().startswith('B') else 8
        if user.class_enrollments.filter(exemption_quota__used_quota__gt=maximum).exists():
            self.add_error('student_code','Mã mới có hạn mức thấp hơn số lượt miễn đã sử dụng.')
        return data

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            for enrollment in user.class_enrollments.select_related('exemption_quota'):
                if hasattr(enrollment,'exemption_quota'):
                    quota = enrollment.exemption_quota
                    quota.max_quota = user.exemption_quota_max
                    quota.save(update_fields=['max_quota', 'updated_at'])
        return user


class ProfileForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = ['first_name','last_name','email','phone_number']


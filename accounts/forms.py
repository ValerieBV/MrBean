from django import forms
from django.contrib.auth.forms import UserCreationForm
from accounts.models import CustomUser


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


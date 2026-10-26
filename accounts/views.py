from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, SetPasswordForm
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from .models import CustomUser, Notification
from .forms import CustomUserCreationForm, CustomUserUpdateForm, ProfileForm
from .permissions import role_required, admin_required


def user_login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard:index')
    form = AuthenticationForm(request, data=request.POST or None)
    target = request.POST.get('next') or request.GET.get('next','')
    if request.method == 'POST' and form.is_valid():
        login(request, form.get_user())
        if target and url_has_allowed_host_and_scheme(target,{request.get_host()},require_https=request.is_secure()):
            return redirect(target)
        return redirect('dashboard:index')
    return render(request,'accounts/login.html',{'form':form,'next':target})


@login_required
@require_POST
def user_logout_view(request):
    logout(request)
    return redirect('accounts:login')


@role_required('admin','manager')
def user_list_view(request):
    rows=CustomUser.objects.all().prefetch_related('class_enrollments__classroom','teaching_classes').order_by('-date_joined')
    role=request.GET.get('role','');query=request.GET.get('q','').strip()[:100]
    if role:rows=rows.filter(role=role)
    if query:rows=rows.filter(Q(username__icontains=query)|Q(first_name__icontains=query)|Q(last_name__icontains=query)|Q(email__icontains=query)|Q(student_code__icontains=query))
    from courses.models import ClassRoom
    return render(request,'accounts/user_list.html',{'users':Paginator(rows,20).get_page(request.GET.get('page')),
        'query':query,'role_filter':role,'role_choices':CustomUser.ROLE_CHOICES,
        'total_students':CustomUser.objects.filter(role='student',is_active=True).count(),
        'total_teachers':CustomUser.objects.filter(role='teacher',is_active=True).count(),
        'active_classes':ClassRoom.objects.filter(is_active=True).count()})


@role_required('admin','manager')
def user_create_view(request):
    form=CustomUserCreationForm(request.POST or None,current_user=request.user)
    if request.method=='POST' and form.is_valid():
        user=form.save();messages.success(request,'Đã tạo tài khoản '+user.username+'.')
        return redirect('accounts:user_list')
    return render(request,'accounts/user_form.html',{'form':form,'title':'Tạo tài khoản','back_url':reverse('accounts:user_list')})


@admin_required
def user_update_view(request,user_id):
    user=get_object_or_404(CustomUser,pk=user_id)
    form=CustomUserUpdateForm(request.POST or None,instance=user)
    if request.method=='POST' and form.is_valid():
        if user.pk==request.user.pk and not form.cleaned_data['is_active']:
            form.add_error('is_active','Không tự ngừng kích hoạt tài khoản đang sử dụng.')
        else:
            form.save();messages.success(request,'Đã cập nhật tài khoản.')
            return redirect('accounts:user_list')
    return render(request,'accounts/user_form.html',{'form':form,'title':'Cập nhật '+user.username,'target_user':user,'back_url':reverse('accounts:user_list')})


@admin_required
def user_delete_view(request,user_id):
    user=get_object_or_404(CustomUser,pk=user_id)
    if request.method=='POST':
        if user.pk==request.user.pk:
            messages.error(request,'Không thể tự vô hiệu hóa tài khoản đang sử dụng.')
        elif user.role=='teacher' and user.teaching_classes.filter(is_active=True).exists():
            messages.error(request,'Phân công giáo viên thay thế cho các lớp đang hoạt động trước.')
        elif (user.role=='admin' or user.is_superuser) and not CustomUser.objects.filter(Q(role='admin')|Q(is_superuser=True),is_active=True).exclude(pk=user.pk).exists():
            messages.error(request,'Cần giữ ít nhất một quản trị viên hoạt động.')
        else:
            user.is_active=False;user.save(update_fields=['is_active'])
            messages.success(request,'Đã vô hiệu hóa tài khoản; lịch sử học tập và điểm được giữ nguyên.')
        return redirect('accounts:user_list')
    return render(request,'accounts/user_confirm_delete.html',{'target_user':user})


@login_required
def profile(request):
    form=ProfileForm(request.POST or None,instance=request.user)
    if request.method=='POST' and form.is_valid():
        form.save();messages.success(request,'Đã cập nhật hồ sơ.')
        return redirect('accounts:profile')
    return render(request,'accounts/profile.html',{'form':form})


@login_required
def password_change(request):
    form=PasswordChangeForm(request.user,request.POST or None)
    if request.method=='POST' and form.is_valid():
        user=form.save();update_session_auth_hash(request,user)
        messages.success(request,'Đã đổi mật khẩu.');return redirect('accounts:profile')
    return render(request,'accounts/user_form.html',{'form':form,'title':'Đổi mật khẩu','back_url':reverse('accounts:profile')})


@admin_required
def password_reset_user(request,user_id):
    user=get_object_or_404(CustomUser,pk=user_id)
    form=SetPasswordForm(user,request.POST or None)
    if request.method=='POST' and form.is_valid():
        form.save();messages.success(request,'Đã đặt lại mật khẩu cho '+user.username+'.')
        return redirect('accounts:user_list')
    return render(request,'accounts/user_form.html',{'form':form,'title':'Đặt mật khẩu cho '+user.username,'back_url':reverse('accounts:user_list')})


@login_required
def notification_list_view(request):
    rows=request.user.notifications.all()
    if request.GET.get('unread')=='1':rows=rows.filter(is_read=False)
    return render(request,'accounts/notifications.html',{'notifications':Paginator(rows,20).get_page(request.GET.get('page')),
        'unread_count':request.user.notifications.filter(is_read=False).count()})


@login_required
@require_POST
def mark_notification_read_view(request,notification_id):
    item=get_object_or_404(Notification,pk=notification_id,recipient=request.user)
    item.is_read=True;item.save(update_fields=['is_read'])
    if request.headers.get('x-requested-with')=='XMLHttpRequest':return JsonResponse({'status':'ok'})
    return redirect(item.safe_target_url if request.POST.get('open') else 'accounts:notification_list')


@login_required
@require_POST
def notifications_read_all(request):
    request.user.notifications.filter(is_read=False).update(is_read=True)
    messages.success(request,'Đã đánh dấu tất cả thông báo là đã đọc.')
    return redirect('accounts:notification_list')

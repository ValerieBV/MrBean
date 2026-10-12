from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from accounts.models import CustomUser, Notification
from accounts.forms import CustomUserCreationForm, CustomUserUpdateForm
from accounts.permissions import role_required, admin_required, manager_required


def user_login_view(request):
    """Đăng nhập hệ thống phân quyền Mr Bean"""
    if request.user.is_authenticated:
        return redirect('courses:class_list')

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, f"Chào mừng {user.get_full_name() or user.username} [{user.get_role_display()}] quay trở lại!")
            return redirect('courses:class_list')
        else:
            messages.error(request, "Tên đăng nhập hoặc mật khẩu không chính xác.")
    else:
        form = AuthenticationForm()

    return render(request, 'accounts/login.html', {'form': form})


@login_required
def user_logout_view(request):
    """Đăng xuất"""
    logout(request)
    messages.info(request, "Bạn đã đăng xuất thành công.")
    return redirect('accounts:login')


@role_required(CustomUser.ROLE_ADMIN, CustomUser.ROLE_MANAGER)
def user_list_view(request):
    """
    Quản lý danh sách người dùng:
    - Admin & Quản lý có quyền xem.
    - Lọc theo vai trò (Admin, Quản lý, Giáo viên, Học viên).
    - Tìm kiếm theo tên đăng nhập, họ tên, email, SĐT.
    """
    role_filter = request.GET.get('role', '')
    query = request.GET.get('q', '')

    users = CustomUser.objects.all().order_by('-date_joined')

    if role_filter:
        users = users.filter(role=role_filter)

    if query:
        users = users.filter(
            username__icontains=query
        ) | users.filter(
            first_name__icontains=query
        ) | users.filter(
            last_name__icontains=query
        ) | users.filter(
            email__icontains=query
        ) | users.filter(
            phone_number__icontains=query
        )

    context = {
        'users': users,
        'role_filter': role_filter,
        'query': query,
        'role_choices': CustomUser.ROLE_CHOICES,
    }
    return render(request, 'accounts/user_list.html', context)


@admin_required
def user_create_view(request):
    """Admin thêm người dùng mới và phân quyền"""
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, f"Đã tạo thành công tài khoản {user.username} với vai trò {user.get_role_display()}.")
            return redirect('accounts:user_list')
    else:
        form = CustomUserCreationForm()

    return render(request, 'accounts/user_form.html', {'form': form, 'title': 'Thêm người dùng mới'})


@admin_required
def user_update_view(request, user_id):
    """Admin chỉnh sửa thông tin và vai trò người dùng"""
    target_user = get_object_or_404(CustomUser, id=user_id)
    if request.method == 'POST':
        form = CustomUserUpdateForm(request.POST, instance=target_user)
        if form.is_valid():
            form.save()
            messages.success(request, f"Đã cập nhật thông tin tài khoản {target_user.username}.")
            return redirect('accounts:user_list')
    else:
        form = CustomUserUpdateForm(instance=target_user)

    return render(request, 'accounts/user_form.html', {'form': form, 'title': f'Chỉnh sửa người dùng: {target_user.username}', 'target_user': target_user})


@admin_required
def user_delete_view(request, user_id):
    """Admin vô hiệu hóa hoặc xóa người dùng"""
    target_user = get_object_or_404(CustomUser, id=user_id)
    if request.method == 'POST':
        if target_user == request.user:
            messages.error(request, "Không thể tự xóa tài khoản của chính mình!")
            return redirect('accounts:user_list')
        
        # An toàn: Soft delete bằng cách set is_active=False hoặc xóa
        username = target_user.username
        target_user.delete()
        messages.success(request, f"Đã xóa người dùng {username} thành công.")
        return redirect('accounts:user_list')

    return render(request, 'accounts/user_confirm_delete.html', {'target_user': target_user})


@login_required
def notification_list_view(request):
    """
    Xem danh sách thông báo:
    - Quản lý nhận thông báo khi có học viên xin miễn / giáo viên duyệt miễn.
    - Giáo viên nhận thông báo khi có đơn xin miễn mới cần duyệt.
    - Học viên nhận thông báo khi đơn được duyệt hoặc bị từ chối.
    """
    notifications = request.user.notifications.all()
    # Tự động đánh dấu đã đọc khi xem
    unread = notifications.filter(is_read=False)
    
    return render(request, 'accounts/notifications.html', {
        'notifications': notifications,
        'unread_count': unread.count()
    })


@login_required
def mark_notification_read_view(request, notification_id):
    """Đánh dấu thông báo đã đọc"""
    noti = get_object_or_404(Notification, id=notification_id, recipient=request.user)
    noti.is_read = True
    noti.save()
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'status': 'ok'})
    return redirect('accounts:notification_list')

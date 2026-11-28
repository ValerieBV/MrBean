from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.shortcuts import redirect
from django.urls import reverse
from accounts.models import CustomUser, Notification


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    """
    Quản trị người dùng trong Django Admin:
    Hỗ trợ lọc theo vai trò (Admin, Quản lý, Giáo viên, Học viên), tìm kiếm nhanh.
    """
    model = CustomUser

    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_admin_user

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_admin_user

    def has_delete_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_admin_user

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop('delete_selected', None)
        return actions

    def delete_view(self, request, object_id, extra_context=None):
        if not self.has_delete_permission(request):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied
        return redirect(reverse('accounts:user_delete', args=[object_id]))

    list_display = (
        'username',
        'email',
        'first_name',
        'last_name',
        'role',
        'phone_number',
        'is_active',
        'is_staff'
    )
    list_filter = ('role', 'is_active', 'is_staff', 'is_superuser')
    search_fields = ('username', 'email', 'first_name', 'last_name', 'phone_number')
    ordering = ('username',)

    fieldsets = UserAdmin.fieldsets + (
        ('Thông tin bổ sung', {'fields': ('role', 'phone_number', 'student_code')}),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Thông tin bổ sung', {
            'classes': ('wide',),
            'fields': ('role', 'phone_number', 'student_code', 'email', 'first_name', 'last_name'),
        }),
    )


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'recipient', 'sender', 'notification_type', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read', 'created_at')
    search_fields = ('title', 'message', 'recipient__username', 'sender__username')
    readonly_fields = ('created_at',)

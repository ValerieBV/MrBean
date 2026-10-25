from ai_core.permissions import is_manager


def navigation(request):
    user = request.user
    if not user.is_authenticated:
        return {}
    return {'is_reporting_staff': is_manager(user) or user.role == 'teacher',
            'is_reporting_manager': is_manager(user),
            'unread_notifications': user.notifications.filter(is_read=False).count()}

from ai_core.permissions import is_manager


def navigation(request):
    user = request.user
    if not user.is_authenticated:
        return {}
    route = request.resolver_match
    name = route.url_name or '' if route else ''
    section = ''
    if route and route.app_name == 'courses':
        section = 'catalog' if name.startswith('course_') else (
            'exemptions' if 'exemption' in name else 'classes')
    elif route and route.app_name == 'accounts' and (name.startswith('user_') or name == 'password_reset'):
        section = 'accounts'
    return {'sidebar_section': section,
            'is_reporting_staff': is_manager(user) or user.role == 'teacher',
            'is_reporting_manager': is_manager(user),
            'unread_notifications': user.notifications.filter(is_read=False).count()}

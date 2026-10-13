from functools import wraps
from django.http import JsonResponse


def is_manager(user):
    return user.is_superuser or user.role in ('admin', 'manager')


def tasks_for(user):
    from dashboard.models import LearningTask
    tasks = LearningTask.objects.all()
    if is_manager(user):
        return tasks
    if user.role == 'teacher':
        return tasks.filter(teacher=user)
    return tasks.filter(learner=user)


def staff_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'authentication_required'}, status=401)
        if not (is_manager(request.user) or request.user.role == 'teacher'):
            return JsonResponse({'error': 'forbidden'}, status=403)
        return view(request, *args, **kwargs)
    return wrapped

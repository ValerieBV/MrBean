from functools import wraps
from django.db.models import Q
from django.http import JsonResponse


def is_manager(user):
    return user.is_superuser or user.role in ('admin', 'manager')


def classes_for(user):
    from courses.models import ClassRoom
    rows = ClassRoom.objects.all()
    if is_manager(user):
        return rows
    if user.role == 'teacher':
        return rows.filter(teacher=user)
    if user.role == 'student':
        return rows.filter(enrollments__student=user, enrollments__status='active').distinct()
    return rows.none()


def tasks_for(user):
    from dashboard.models import LearningTask
    tasks = LearningTask.objects.all()
    if is_manager(user):
        return tasks
    if user.role == 'teacher':
        return tasks.filter(Q(assignment__classroom__teacher=user) | Q(assignment__isnull=True, teacher=user))
    if user.role == 'student':
        return tasks.filter(learner=user)
    return tasks.none()


def staff_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'authentication_required'}, status=401)
        if not (is_manager(request.user) or request.user.role == 'teacher'):
            return JsonResponse({'error': 'forbidden'}, status=403)
        return view(request, *args, **kwargs)
    return wrapped

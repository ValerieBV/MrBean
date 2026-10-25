from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET
from ai_core.permissions import classes_for, is_manager
from .services import metrics_for


@require_GET
@login_required
def index(request):
    template = 'dashboard/student.html' if request.user.role == 'student' and not request.user.is_superuser else 'dashboard/staff.html'
    return render(request, template, {'classes': classes_for(request.user).order_by('class_code'),
        'dashboard_title': 'Tổng quan quản lý' if is_manager(request.user) else 'Lớp học và bài cần chấm'})


@require_GET
def metrics(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'authentication_required'}, status=401)
    try:
        if request.GET.get('classroom'):
            int(request.GET['classroom'])
        data = metrics_for(request.user, filters=request.GET)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'invalid_filter'}, status=400)
    response = JsonResponse(data)
    response['Cache-Control'] = 'private, no-store'
    return response

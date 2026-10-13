from django.http import JsonResponse
from django.conf import settings
from django.shortcuts import render
from django.views.decorators.http import require_GET
from ai_core.permissions import staff_required
from .services import metrics_for


@require_GET
@staff_required
def index(request):
    return render(request, 'dashboard/index.html', {
        'sla_warning_hours': settings.SLA_WARNING_HOURS,
        'dropout_missed_tasks': settings.DROPOUT_MISSED_TASKS,
        'dropout_inactive_days': settings.DROPOUT_INACTIVE_DAYS,
    })


@require_GET
@staff_required
def metrics(request):
    response = JsonResponse(metrics_for(request.user))
    response['Cache-Control'] = 'private, no-store'
    return response

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


@require_GET
@login_required
def export_csv(request):
    import csv
    from django.http import HttpResponse
    from .services import annotated_tasks
    try: rows = annotated_tasks(request.user, request.GET)
    except (ValueError, TypeError): return JsonResponse({'error':'invalid_filter'}, status=400)
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="mrbean-ket-qua.csv"'
    response['Cache-Control'] = 'private, no-store'
    response.write('\ufeff')
    writer = csv.writer(response)
    writer.writerow(['Lớp','Mã học viên','Học viên','Bài tập','Hạn nộp','Trạng thái','Điểm chính thức /10','Điểm AI gợi ý /10'])
    from .services import task_state
    from django.utils import timezone
    def safe(value):
        text = str(value) if value is not None else ''
        return "'"+text if text.lstrip().startswith(('=','+','-','@','\t','\r')) else text
    labels = {'not_submitted':'Chưa nộp','exempt':'Được miễn','exemption_pending':'Chờ duyệt miễn',
        'queued':'Chờ AI','processing':'AI đang chấm','ai_reviewed':'AI gợi ý, chờ xác nhận',
        'manual':'Chờ giáo viên','graded':'Đã có điểm','locked':'Chưa mở','closed':'Đã đóng'}
    for task in rows.iterator():
        state, _ = task_state(task, timezone.now())
        writer.writerow([safe(v) for v in [task.assignment.classroom.class_code if task.assignment_id else 'Bài cũ',
            task.learner.student_code, task.learner.get_full_name() or task.learner.username, task.title,
            timezone.localtime(task.due_at).strftime('%d/%m/%Y %H:%M'), labels.get(state,state), task.confirmed_score, task.ai_score]])
    return response

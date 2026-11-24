import csv

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from ai_core.permissions import is_manager
from ai_core.reporting import REPORT_STATUS_LABELS
from .cohort import AI, FOCUS, SKILLS, STAGES, Cohort, duplicate_codes
from .query import class_options, learner_classes, roster, student_label
from .services import metrics_for


def is_staff_view(user):
    return is_manager(user) or user.role == 'teacher'


def target(user, learner_id):
    if learner_id is None:
        return None
    if not is_staff_view(user):
        raise Http404
    return get_object_or_404(roster(user, historical=True).only('pk', 'student_code'), pk=learner_id)


def report_url(name, learner):
    return reverse('dashboard:learner_' + name, args=[learner.pk]) if learner else reverse('dashboard:' + name)


@require_GET
@login_required
@never_cache
def index(request, learner_id=None):
    user = request.user
    learner = target(user, learner_id)
    staff = is_staff_view(user)
    overview = staff and learner is None
    classes = class_options(user)
    if learner:
        classes = classes.filter(pk__in=learner_classes(learner).values('pk'))
    code = student_label(learner.pk, learner.student_code, duplicate_codes(user)) if learner else (
        '' if staff else student_label(user.pk, user.student_code))
    title = ('Tiến độ học viên ' + code if learner else 'Bài tập và kết quả của tôi' if not staff else
             'Tổng quan quản lý' if is_manager(user) else 'Lớp học và bài cần chấm')
    return render(request, 'dashboard/staff.html' if staff else 'dashboard/student.html', {
        'dashboard_title': title, 'overview': overview, 'learner_detail': bool(learner), 'student_code': code,
        'metrics_url': report_url('metrics', learner), 'export_url': report_url('export', learner),
        'classes': classes.order_by('class_code'), 'stage_options': STAGES, 'skill_options': SKILLS,
        'focus_options': FOCUS, 'ai_options': AI, 'can_confirm': user.is_superuser or user.role in ('admin', 'teacher'),
    })


@require_GET
@never_cache
def metrics(request, learner_id=None):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'authentication_required'}, status=401)
    learner = target(request.user, learner_id)
    try:
        return JsonResponse(metrics_for(request.user, filters=request.GET, learner=learner))
    except (ValueError, OverflowError):
        return JsonResponse({'error': 'invalid_filter'}, status=400)


def safe_csv(value):
    value = '' if value is None else str(value)
    return "'" + value if value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r', '\n')) else value


@require_GET
@login_required
@never_cache
def export_csv(request, learner_id=None):
    learner = target(request.user, learner_id)
    try:
        cohort = Cohort(request.user, request.GET, timezone.now(), learner)
    except (ValueError, OverflowError):
        return JsonResponse({'error': 'invalid_filter'}, status=400)
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="mrbean-ket-qua.csv"'
    response.write('\ufeff')
    writer = csv.writer(response)
    writer.writerow(['Lớp', 'Mã học viên', 'Kỹ năng', 'Bài tập', 'Hạn nộp', 'Đã nộp / số bài nghe',
                     'Tiến độ hiện tại', 'Trạng thái', 'Nhận xét giáo viên'])
    for f in cohort.rows:
        t = f.task
        writer.writerow(map(safe_csv, [f.classroom, cohort.labels[t.learner_id], SKILLS[f.skill], t.title,
            timezone.localtime(t.due_at).strftime('%d/%m/%Y %H:%M'), f'{f.submitted_parts}/{f.parts}' if f.parts else '',
            STAGES[f.stage], REPORT_STATUS_LABELS.get(f.state, f.state), t.confirmed_feedback]))
    return response

from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta

from django.conf import settings
from django.db.models import Count, Func, IntegerField, Max, OuterRef, Subquery
from django.db.models.functions import Lower, Trim
from django.urls import reverse
from django.utils import timezone

from ai_core.models import GradingJob
from ai_core.permissions import is_manager, tasks_for
from .query import annotated_tasks, code_search, roster, student_label, task_state


SKILLS = {'listening': 'Nghe', 'speaking': 'Nói', 'vocabulary': 'Từ vựng', 'legacy': 'Bài cũ'}
STAGES = {'todo': 'Chưa nộp', 'draft': 'Đang làm', 'partial': 'Đã nộp một phần',
          'revise': 'Cần bổ sung', 'processing': 'Đang xử lý', 'review': 'Chờ giáo viên',
          'complete': 'Hoàn thành', 'blocked': 'Chưa thể nộp', 'exemption_pending': 'Chờ duyệt miễn', 'exempt': 'Được miễn'}
FOCUS = {'submitted': 'Đã có bài nộp', 'full': 'Đã nộp đủ các phần', 'complete': 'Đã xác nhận hoàn thành',
         'on_time': 'Hoàn thành đúng hạn', 'action': 'Học viên cần làm', 'overdue': 'Quá hạn chưa hoàn thành',
         'risk': 'Bài quá hạn của học viên cần hỗ trợ', 'review': 'Chờ giáo viên'}
AI = {'timely': 'Có đề xuất đúng hạn', 'late': 'Có đề xuất trễ', 'manual': 'Chuyển chấm thủ công',
      'waiting': 'Đang xử lý', 'unknown': 'Thiếu dữ liệu thời gian'}


def validate(filters, staff):
    for key, allowed in [('skill', SKILLS), ('stage', STAGES), ('focus', FOCUS),
                         ('ai', AI if staff else ()), ('scope', ('live', 'all'))]:
        if filters.get(key) and filters[key] not in allowed:
            raise ValueError(key)
    if classroom := filters.get('classroom'):
        if classroom != 'legacy' and (not str(classroom).isascii() or not str(classroom).isdigit() or not 0 < int(classroom) < 2**63):
            raise ValueError('classroom')
    dates = {key: date.fromisoformat(filters[key]) for key in ('date_from', 'date_to', 'week') if filters.get(key)}
    if dates.get('date_from', date.min) > dates.get('date_to', date.max):
        raise ValueError('date_range')
    if 'week' in dates and (dates['week'].weekday() or dates['week'] > date.max - timedelta(days=6)):
        raise ValueError('week')


class ArraySize(Func):
    function = 'JSON_ARRAY_LENGTH'
    output_field = IntegerField()

    def as_postgresql(self, compiler, connection, **extra):
        return self.as_sql(compiler, connection, function='jsonb_array_length', **extra)


def duplicate_codes(user):
    people = roster(user, historical=True).exclude(student_code__isnull=True).exclude(student_code='')
    return set(people.order_by().values(code=Lower(Trim('student_code'))).annotate(n=Count('pk')).filter(n__gt=1).values_list('code', flat=True))


def percent(n, total):
    return round(n * 100 / total, 2) if total else 0


@dataclass
class TaskFact:
    task: object
    state: str
    blocked: str
    stage: str
    skill: str
    classroom: str
    class_key: str
    week: str
    submitted_parts: int
    parts: int
    submitted: bool
    full: bool
    complete: bool
    on_time: bool
    overdue: bool
    actionable: bool
    ai: str

    @classmethod
    def read(cls, t, now, staff):
        modern = t.assignment_id is not None
        skill = t.assignment.lesson.skill if modern else 'legacy'
        state, blocked = task_state(t, now)
        submitted = bool(t.latest_job_id) and not t.exemption_id
        complete = not t.exemption_id and t.confirmed_completion == 'complete'
        parts = (t.listening_total or t.assigned_parts or 1) if skill == 'listening' else 0
        count = t.listening_submitted if t.listening_submitted is not None else (t.snapshot_parts or int(submitted and parts == 1))
        partial = bool(submitted and parts and count < parts)
        if t.exemption_id:
            stage = 'exempt'
        elif t.latest_status in ('manual', 'ai_reviewed') or (t.latest_status == 'graded' and t.confirmed_completion == 'pending'):
            stage = 'review'
        elif t.latest_status in ('queued', 'processing'):
            stage = 'processing'
        elif complete:
            stage = 'complete'
        elif t.pending_exemption_id:
            stage = 'exemption_pending'
        elif blocked or not modern:
            stage = 'blocked'
        elif partial:
            stage = 'partial'
        elif t.confirmed_completion == 'incomplete':
            stage = 'revise'
        else:
            stage = 'draft' if t.has_draft else 'todo'
        live = t.learner.is_active and (not modern or (t.assignment.is_active and t.assignment.classroom.is_active and t.current_enrollment))
        overdue = bool(live and t.due_at < now and not complete and not t.exemption_id and not t.pending_exemption_id
                       and stage not in ('review', 'processing') and not (modern and t.assignment.requires_previous and t.earlier_unfinished))
        day = timezone.localdate(t.assigned_at)
        ai = ''
        if staff and getattr(t, 'job_kind', None) in ('speaking', 'vocabulary') and not t.exemption_id:
            if t.proposal_at:
                ai = 'timely' if t.proposal_at <= t.latest_at + timedelta(seconds=settings.AI_DEADLINE_SECONDS) else 'late'
            elif t.latest_status == 'manual' or t.manual_reason:
                ai = 'manual'
            elif t.latest_status in ('queued', 'processing'):
                ai = 'waiting'
            else:
                ai = 'unknown'
        return cls(t, state, blocked, stage, skill, t.assignment.classroom.class_code if modern else 'Bài cũ',
                   str(t.assignment.classroom_id) if modern else 'legacy', (day - timedelta(days=day.weekday())).isoformat(),
                   count, parts, submitted, submitted and not partial, complete,
                   bool(complete and t.confirmed_submission_at <= t.due_at), overdue,
                   stage in ('todo', 'draft', 'partial', 'revise'), ai)

    def matches(self, filters, risk_ids):
        focus = filters.get('focus')
        return ((not filters.get('stage') or filters['stage'] == self.stage)
                and (not filters.get('ai') or filters['ai'] == self.ai)
                and (not focus or {'submitted': self.submitted, 'full': self.full, 'complete': self.complete,
                       'on_time': self.on_time, 'action': self.actionable, 'overdue': self.overdue,
                       'risk': self.overdue and self.task.learner_id in risk_ids, 'review': self.stage == 'review'}[focus]))

    def row(self, label, staff):
        t = self.task
        url = reverse('submissions:result', args=[t.latest_job_id]) if t.latest_job_id else None
        submit_url = reverse('submissions:do_task', args=[t.pk]) if t.assignment_id and not staff else None
        if staff and (url or t.assignment_id):
            action_url, action = (url, 'Mở bài nộp') if url else (reverse('assignments:assigned_detail', args=[t.assignment_id]), 'Xem lượt giao')
        elif submit_url and (self.actionable or not url):
            action_url, action = submit_url, ('Tiếp tục làm' if self.stage in ('draft', 'partial') else 'Làm bài') if self.actionable else 'Xem yêu cầu'
        else:
            action_url, action = url, 'Xem kết quả' if t.latest_status == 'graded' else 'Xem bài nộp'
        return dict(id=t.pk, title=t.title, student_code=label, learner_id=t.learner_id, classroom=self.classroom,
                    learner_url=reverse('dashboard:learner', args=[t.learner_id]) if staff else None,
                    skill=self.skill, due_at=t.due_at.isoformat(), latest_status=self.state, stage=self.stage,
                    completion_status=t.confirmed_completion or 'pending', completion_label=STAGES[self.stage],
                    completed_on_time=self.on_time, processing_status=t.latest_status, is_late=self.overdue,
                    resubmission_pending=bool(t.confirmed_job_id and t.latest_status != 'graded'),
                    blocked_reason=self.blocked, submitted_exercise_count=self.submitted_parts, exercise_count=self.parts,
                    action_url=action_url, action_label=action, submit_url=submit_url, result_url=url)


class Cohort:
    def __init__(self, user, filters, now, learner=None):
        self.staff = is_manager(user) or user.role == 'teacher'
        validate(filters, self.staff)
        self.user, self.filters, self.now = user, filters, now
        self.duplicates = duplicate_codes(user) if self.staff else set()
        tasks = annotated_tasks(user, filters, now)
        if learner is not None:
            tasks = tasks.filter(learner=learner)
        last = GradingJob.objects.filter(task_id=OuterRef('pk'), submitted_at__lte=now).order_by('-submitted_at', '-pk')
        tasks = tasks.annotate(assigned_parts=ArraySize('assignment__rubric__exercises'),
            snapshot_parts=Subquery(last.annotate(n=ArraySize('rubric_snapshot__exercises')).values('n')[:1]),
            listening_submitted=Subquery(last.values('result__submitted_exercise_count')[:1], output_field=IntegerField()),
            listening_total=Subquery(last.values('result__exercise_count')[:1], output_field=IntegerField()))
        if self.staff:
            tasks = tasks.annotate(job_kind=Subquery(last.values('kind')[:1]),
                                   proposal_at=Subquery(last.values('ai_assessed_at')[:1]),
                                   manual_reason=Subquery(last.values('fallback_reason')[:1]))
        base = [TaskFact.read(t, now, self.staff) for t in tasks]
        self.risks = self.risk_signals(base)
        self.rows = [f for f in base if f.matches(filters, self.risks)]
        self.labels = {f.task.learner_id: student_label(f.task.learner_id, f.task.learner.student_code, self.duplicates) for f in self.rows}
        self.people = dict(self.labels)
        if self.staff and not any(filters.get(k) for k in ('skill','stage','focus','week','date_from','date_to','ai')):
            people = roster(user, historical=filters.get('scope') == 'all', classroom=filters.get('classroom', ''), now=now)
            if learner is not None:
                people = people.filter(pk=learner.pk)
            if q := filters.get('q', '').strip()[:100]:
                people = people.filter(code_search(q))
            for pk, code in people.values_list('pk', 'student_code'):
                self.people[pk] = student_label(pk, code, self.duplicates)

    def risk_signals(self, base):
        missed, first = Counter(), {}
        for f in base:
            pk = f.task.learner_id
            first[pk] = min(first.get(pk, f.task.assigned_at), f.task.assigned_at)
            if f.overdue:
                missed[pk] += 1
        if not missed:
            return {}
        # A skill/date selection must not erase recent activity in another visible task.
        visible = tasks_for(self.user).filter(learner_id__in=missed, assigned_at__lte=self.now)
        last = dict(GradingJob.objects.filter(task__in=visible, submitted_at__lte=self.now).order_by()
                    .values('task__learner_id').annotate(last=Max('submitted_at')).values_list('task__learner_id', 'last'))
        return {pk: ('missed_tasks' if n >= settings.DROPOUT_MISSED_TASKS else 'inactive', last.get(pk))
                for pk, n in missed.items() if n >= settings.DROPOUT_MISSED_TASKS or
                self.now - (last.get(pk) or first[pk]) >= timedelta(days=settings.DROPOUT_INACTIVE_DAYS)}

from collections import Counter, defaultdict
from itertools import islice

from django.conf import settings
from django.core.paginator import Paginator
from django.urls import reverse
from django.utils import timezone

from ai_core.diagnostics import review_status_label
from ai_core.models import GradingJob
from ai_core.reporting import report_job
from support.permissions import conversations_for
from .cohort import Cohort, STAGES, SKILLS, AI, percent
from .query import annotated_tasks, task_state  # also used by the practice and reporting views


DASHBOARD_PAGE_SIZE = 5


def paginate(rows, number):
    page = Paginator(rows, DASHBOARD_PAGE_SIZE).get_page(number)
    return list(page), {'page': page.number, 'pages': page.paginator.num_pages, 'total': page.paginator.count}


def totals(rows):
    return dict(assigned=sum(f.stage != 'exempt' for f in rows), submitted=sum(f.submitted for f in rows),
                full=sum(f.full for f in rows), completed=sum(f.complete for f in rows),
                on_time=sum(f.on_time for f in rows), action=sum(f.actionable for f in rows),
                review=sum(f.stage == 'review' for f in rows), overdue=sum(f.overdue for f in rows))


def series(rows, key, labels):
    groups = defaultdict(list)
    for f in rows:
        groups[getattr(f, key)].append(f)
    return [dict(key=k, label=labels.get(k, k), total=len(group), **totals(group)) for k, group in sorted(groups.items())]


def people_and_risks(cohort):
    groups = defaultdict(list)
    for f in cohort.rows:
        groups[f.task.learner_id].append(f)
    people, risks = [], []
    for pk, code in cohort.people.items():
        facts = groups[pk]
        row = totals(facts)
        row.update(learner_id=pk, student_code=code, exempt=len(facts)-row['assigned'],
                   completion_rate=percent(row['completed'], row['assigned']),
                   submission_rate=percent(row['submitted'], row['assigned']),
                   graded=sum(f.submitted and f.task.latest_status == 'graded' for f in facts),
                   awaiting_grade=sum(f.submitted and f.task.latest_status != 'graded' for f in facts),
                   resubmissions_pending=sum(bool(f.task.confirmed_job_id and f.task.latest_status != 'graded') for f in facts),
                   detail_url=reverse('dashboard:learner', args=[pk]) if cohort.staff else None)
        people.append(row)
        if row['overdue'] and pk in cohort.risks:
            reason, last = cohort.risks[pk]
            risks.append(dict(learner_id=pk, student_code=code, missed_tasks=row['overdue'], reason=reason,
                              last_submission_at=last.isoformat() if last else None, detail_url=row['detail_url'],
                              incomplete_tasks=sum(f.overdue and f.stage == 'revise' for f in facts)))
    people.sort(key=lambda item: (item['student_code'].casefold(), item['learner_id']))
    risks.sort(key=lambda item: (-item['missed_tasks'], item['student_code'].casefold(), item['learner_id']))
    return people, risks


def metrics_for(user, now=None, filters=None, learner=None):
    now, filters = now or timezone.now(), filters or {}
    cohort = Cohort(user, filters, now, learner)
    facts, staff = cohort.rows, cohort.staff
    summary = totals(facts)
    counts = Counter(f.stage for f in facts)
    people, risks = people_and_risks(cohort)
    class_names = {f.class_key: f.classroom for f in facts}
    ai = Counter(f.ai for f in facts if f.ai)
    measured = ai['timely'] + ai['late'] + ai['manual']
    response = dict(role='admin' if user.is_superuser else user.role, updated_at=now.isoformat(),
                    assigned_count=summary['assigned'], submitted_count=summary['submitted'], full_count=summary['full'],
                    completed_count=summary['completed'], on_time_completed_count=summary['on_time'],
                    incomplete_count=sum(f.task.confirmed_completion == 'incomplete' and f.stage != 'exempt' for f in facts),
                    exempt_count=counts['exempt'], exemption_pending_count=counts['exemption_pending'],
                    completion_rate=percent(summary['completed'], summary['assigned']),
                    submission_rate=percent(summary['submitted'], summary['assigned']),
                    full_rate=percent(summary['full'], summary['assigned']),
                    action_count=summary['action'], overdue_count=summary['overdue'], risk_count=len(risks),
                    class_count=len(set(class_names)-{'legacy'}), learner_count=len(people), task_count=len(facts),
                    charts={'skill': series(facts, 'skill', SKILLS), 'classroom': series(facts, 'class_key', class_names),
                            'week': series(facts, 'week', {}),
                            'stage': [dict(key=k, label=v, total=counts[k]) for k, v in STAGES.items() if counts[k]]})
    if staff:
        response['manual_review_count'] = sum(f.stage == 'review' and f.ai == 'manual' for f in facts)
        response['ai_operations'] = dict(deadline_minutes=settings.AI_DEADLINE_SECONDS/60, total=sum(ai.values()),
            measured=measured, timely_rate=percent(ai['timely'], measured) if measured else None,
            groups=[dict(key=k, label=v, total=ai[k]) for k, v in AI.items() if ai[k]])

    jobs = GradingJob.objects.filter(task_id__in=[f.task.pk for f in facts], submitted_at__lte=now).select_related(
        'task').only('task__learner_id',
        'task__title', 'kind', 'status', 'completion_status', 'submitted_at', 'teacher_feedback', 'finished_at')
    history = jobs.order_by('-submitted_at', '-pk')
    queue_ids = [f.task.latest_job_id for f in facts if f.stage == 'review'] if staff else []
    queue = jobs.filter(pk__in=queue_ids).order_by('submitted_at', 'pk')

    def job_row(job):
        row = report_job(job, include_name=False)
        row.update(student_code=cohort.labels[job.task.learner_id],
                   learner_url=reverse('dashboard:learner', args=[job.task.learner_id]) if staff else None)
        return row

    def add_page(key, parameter, items, format_row=None):
        page, meta = paginate(items, filters.get(parameter + '_page'))
        response[key] = [format_row(item) for item in page] if format_row else page
        response[parameter + '_pagination'] = meta
        return meta['total']

    def task_row(f):
        return f.row(cohort.labels[f.task.learner_id], staff)

    ordered = sorted(facts, key=lambda f: (not f.actionable, not f.overdue, f.task.due_at, f.task.pk))
    response['next_tasks'] = [task_row(f) for f in islice((f for f in ordered if f.actionable), 3)]
    add_page('tasks', 'tasks', ordered, task_row)
    add_page('learner_progress', 'progress', people)
    add_page('at_risk_learners', 'risks', risks)
    response['graded_count'] = add_page('graded_report', 'grades', history.filter(status='graded'), job_row)
    add_page('history', 'history', history, job_row)
    response['review_queue_count'] = add_page('review_queue', 'queue', queue,
        lambda job: dict(job_row(job), review_status_label=review_status_label(job)))

    if staff:
        waiting = conversations_for(user).filter(kind='knowledge', status='waiting',
            job__task_id__in=[f.task.pk for f in facts]).select_related(None).select_related('job__task').only(
                'job__task__title', 'job__task__learner_id', 'escalated_at').order_by('escalated_at', 'pk')
        response['support_count'] = add_page('support_queue', 'support', waiting, lambda c: dict(
            title=c.job.task.title, student_code=cohort.labels[c.job.task.learner_id],
            learner_url=reverse('dashboard:learner', args=[c.job.task.learner_id]), detail_url=c.get_absolute_url(), since=c.escalated_at.isoformat() if c.escalated_at else None))
    return response

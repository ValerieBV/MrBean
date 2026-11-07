from django.db import migrations


def restore_assessment(apps, schema_editor):
    Job = apps.get_model('ai_core', 'GradingJob')
    Progress = apps.get_model('submissions', 'LessonProgress')
    # Listening has objective evidence of whether every required field was filled.
    # Scores and teacher feedback are never rewritten or used to guess completion.
    for job in Job.objects.filter(status='graded', kind='listening').iterator():
        questions = (job.rubric_snapshot or {}).get('questions', [])
        if not isinstance(questions, list) or not questions or not isinstance(job.answers, dict):
            continue
        filled, valid = [], True
        for q in questions:
            if not isinstance(q, dict) or 'id' not in q:
                valid = False
                break
            raw = job.answers.get(str(q['id']), '')
            choice = raw.get('chosen', '') if isinstance(raw, dict) else raw
            text = raw.get('short_answer', '') if isinstance(raw, dict) else ''
            if not isinstance(choice, str) or not isinstance(text, str):
                valid = False
                break
            letters = q.get('choice_letters', 'ABCD')
            if letters not in ('ABC', 'ABCD') or choice.strip().upper() not in ('', *letters):
                valid = False
                break
            filled.append(bool(choice.strip()) and (bool(text.strip()) or not q.get('requires_short_answer', False)))
        if valid:
            Job.objects.filter(pk=job.pk).update(completion_status='complete' if all(filled) else 'incomplete',
                completion_confirmed_at=job.finished_at)
    # Repair integrated progress that previously became "completed" on submit.
    ids = Job.objects.exclude(progress_id=None).values_list('progress_id', flat=True).distinct()
    for progress_id in ids.iterator():
        latest = Job.objects.filter(progress_id=progress_id).order_by('-submitted_at', '-pk').first()
        final = Job.objects.filter(task_id=latest.task_id, status='graded').order_by('-submitted_at', '-pk').first()
        state = {'complete': 'completed', 'incomplete': 'incomplete'}.get(final.completion_status, 'assessed') if final else 'submitted'
        Progress.objects.filter(pk=progress_id).update(status=state,
            completed_at=final.submitted_at if final and final.completion_status=='complete' else None)


class Migration(migrations.Migration):
    dependencies = [('ai_core', '0004_gradingjob_completion_confirmed_at_and_more'),
                    ('submissions', '0002_alter_lessonprogress_status')]
    operations = [migrations.RunPython(restore_assessment, migrations.RunPython.noop)]

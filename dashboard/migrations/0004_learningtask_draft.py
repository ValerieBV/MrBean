from django.db import migrations, models


def copy_unambiguous_drafts(apps, schema_editor):
    alias = schema_editor.connection.alias
    Progress = apps.get_model('submissions', 'LessonProgress')
    Task = apps.get_model('dashboard', 'LearningTask')
    rows = Progress.objects.using(alias).filter(draft_saved_at__isnull=False).exclude(draft={})
    for progress in rows.iterator(chunk_size=200):
        candidates = list(Task.objects.using(alias).filter(
            learner_id=progress.student_id, assignment__lesson_id=progress.lesson_id
        ).values_list('pk', flat=True)[:2])
        if len(candidates) == 1:
            Task.objects.using(alias).filter(pk=candidates[0]).update(
                draft=progress.draft, draft_saved_at=progress.draft_saved_at)


class Migration(migrations.Migration):
    dependencies = [
        ('dashboard', '0003_learningtask_exemption'),
        ('submissions', '0002_alter_lessonprogress_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='learningtask', name='draft',
            field=models.JSONField(blank=True, default=dict, verbose_name='Bản nháp của lượt giao'),
        ),
        migrations.AddField(
            model_name='learningtask', name='draft_saved_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(copy_unambiguous_drafts, migrations.RunPython.noop),
    ]

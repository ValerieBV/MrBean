from django.db import migrations, models
from django.db.models import F


def known_proposals(apps, schema_editor):
    jobs = apps.get_model('ai_core', 'GradingJob').objects.using(schema_editor.connection.alias)
    jobs.filter(status='ai_reviewed', kind__in=('speaking', 'vocabulary'), finished_at__isnull=False).update(
        ai_assessed_at=F('finished_at'), ai_assessment_method=F('grading_method'))


class Migration(migrations.Migration):
    dependencies = [('ai_core', '0005_assess_completion_history')]
    operations = [
        migrations.AddField(model_name='gradingjob', name='ai_assessed_at', field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='gradingjob', name='ai_assessment_method', field=models.CharField(blank=True, max_length=20)),
        migrations.RunPython(known_proposals, migrations.RunPython.noop),
    ]

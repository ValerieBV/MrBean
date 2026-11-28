from django.db import migrations


def preserve_existing(apps, schema_editor):
    Lesson = apps.get_model('assignments', 'Lesson')
    Exercise = apps.get_model('assignments', 'ListeningExercise')
    Question = apps.get_model('assignments', 'ListeningQuestion')
    for lesson in Lesson.objects.filter(skill='listening').iterator():
        rows = list(Question.objects.filter(lesson_id=lesson.pk, exercise__isnull=True).order_by('order', 'pk'))
        if not rows:
            continue
        exercise = Exercise.objects.create(lesson_id=lesson.pk, order=1, kind='legacy',
            title='Nội dung nghe đã có', audio_file=lesson.audio_file, question_count=len(rows))
        for number, question in enumerate(rows, 1):
            question.exercise_id, question.order = exercise.pk, number
        Question.objects.bulk_update(rows, ['exercise', 'order'])


class Migration(migrations.Migration):
    dependencies = [('assignments', '0005_listeningexercise_listeningquestion_exercise_and_more')]
    operations = [migrations.RunPython(preserve_existing, migrations.RunPython.noop)]

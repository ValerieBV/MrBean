import re
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from accounts.permissions import can_assign_homework_to_class
from .models import ClassAssignment, Lesson, ListeningExercise, ListeningQuestion
from .listening import LISTENING_SPECS


@transaction.atomic
def save_listening_exercise(*, actor, form):
    from ai_core.permissions import is_manager
    lesson = Lesson.objects.select_for_update().get(pk=form.instance.lesson_id)
    if not (is_manager(actor) or actor.role == 'teacher' and lesson.created_by_id == actor.pk):
        raise PermissionDenied
    if lesson.class_assignments.exists() or lesson.progress.exists():
        raise ValidationError('Buổi đã được sử dụng. Sao chép buổi trước khi đổi bài nghe.')
    if not form.instance.pk and lesson.listening_exercises.count() >= 4:
        raise ValidationError('Mỗi buổi chỉ có từ 1 đến 4 bài nghe.')
    exercise = form.save(commit=False)
    exercise.lesson = lesson
    exercise.full_clean()
    exercise.save()
    existing = {q.order: q for q in exercise.questions.all()}
    for row in form.cleaned_data['answer_rows']:
        question = existing.get(row['number']) or ListeningQuestion(lesson=lesson, exercise=exercise, order=row['number'])
        question.correct_option = row['answer']
        if 'question_text' in row:
            question.question_text = row['question_text']
        for letter in 'ABCD':
            key = 'option_' + letter.lower()
            setattr(question, key, (row.get(key, getattr(question, key)) or letter) if letter in exercise.choice_letters else '')
        question.full_clean()
        question.save()
    exercise.questions.exclude(order__in=range(1, exercise.question_count + 1)).delete()
    return exercise


def lesson_rubric(lesson, repetitions=1):
    data = {'description': lesson.description, 'skill': lesson.skill, 'title': lesson.title,
            'audio_name': lesson.audio_file.name if lesson.audio_file else ''}
    if lesson.skill == 'listening':
        exercises = list(lesson.listening_exercises.prefetch_related('questions'))
        if len(exercises) > 4:
            raise ValidationError('Một buổi chỉ được giao từ 1 đến 4 bài nghe.')
        questions, groups = [], []
        if exercises:
            if lesson.questions.filter(exercise__isnull=True).exists():
                raise ValidationError('Có câu hỏi chưa thuộc bài nghe. Kiểm tra lại buổi trước khi giao.')
            for exercise in exercises:
                items = list(exercise.questions.order_by('order', 'pk'))
                expected = LISTENING_SPECS[exercise.kind]['count'] or exercise.question_count
                if len(items) != expected or [q.order for q in items] != list(range(1, expected + 1)):
                    raise ValidationError(f'Bài {exercise.order} cần đủ {expected} câu, đánh số liên tục.')
                if not exercise.audio_file:
                    raise ValidationError(f'Bài {exercise.order} chưa có file nghe.')
                if exercise.kind == 'part1' and not exercise.document_file:
                    raise ValidationError('Bài Mô tả tranh cần PDF đề bài để xem trên web.')
                group = {'id': exercise.pk, 'order': exercise.order, 'kind': exercise.kind,
                    'label': exercise.get_kind_display(), 'title': exercise.display_title,
                    'question_count': len(items), 'audio_name': exercise.audio_file.name,
                    'document_name': exercise.document_file.name, 'question_ids': [q.pk for q in items]}
                groups.append(group)
                for q in items:
                    row = {k: getattr(q, k) for k in ('id', 'question_text', 'option_a', 'option_b', 'option_c', 'option_d', 'correct_option', 'correct_answer')}
                    if q.correct_option not in exercise.choice_letters:
                        raise ValidationError(f'Bài {exercise.order}, câu {q.order}: đáp án không đúng dạng bài.')
                    row.update(exercise_id=exercise.pk, exercise_order=exercise.order, number=q.order,
                        choice_letters=exercise.choice_letters, requires_short_answer=True,
                        image_name=q.image.name if q.image else '')
                    questions.append(row)
        else:
            # Preserve source-branch lessons until their existing content is reorganized.
            questions = list(lesson.questions.values('id', 'question_text', 'option_a', 'option_b', 'option_c', 'option_d', 'correct_option', 'correct_answer'))
            for number, q in enumerate(questions, 1):
                q.update(number=number, choice_letters='ABCD', requires_short_answer=True)
        if not questions or any(q['correct_option'] not in 'ABCD' or len(q['correct_option']) != 1 or not q['option_'+q['correct_option'].lower()] for q in questions):
            raise ValidationError('Mỗi câu nghe phải có lựa chọn và đáp án A–D hợp lệ trước khi giao bài.')
        data.update(questions=questions, exercises=groups, completion_rule='all_choices_and_short_answers')
        images = dict(lesson.questions.values_list('pk','image'))
        for question in questions:
            question['image_name'] = images.get(question['id']) or ''
    elif lesson.skill == 'vocabulary':
        unique_words = {}
        for word in lesson.words.values_list('word', flat=True):
            if word.strip():
                unique_words.setdefault(re.sub(r'\s+', ' ', word.strip().casefold()), word.strip())
        words = list(unique_words.values())
        if not words:
            raise ValidationError('Chưa có từ vựng trong buổi học.')
        data.update(words=words, repetitions=repetitions)
        data['word_details'] = list(lesson.words.values('word','word_type','meaning','example'))
    else:
        from .video import youtube_embed
        from ai_core.reading import words, MAX_REFERENCE_WORDS
        reference = lesson.reference_transcript.strip()
        if len(reference) > 20000 or not 1 <= len(words(reference)) <= MAX_REFERENCE_WORDS:
            raise ValidationError('Cần lời mẫu chính xác từ 1 đến 1500 từ cho bài đọc theo video.')
        data.update(mode='repeat_video', reference_transcript=reference,
            video_name=lesson.video_file.name if lesson.video_file else '',
            video_embed_url='' if lesson.video_file else youtube_embed(lesson.youtube_url),
            youtube_url='' if lesson.video_file else lesson.youtube_url)

    return data


@transaction.atomic
def assign_to_class(*, actor, lesson, classroom, assigned_at, due_at, repetitions=1,
                    allow_late_submission=True, requires_previous=True):
    if not can_assign_homework_to_class(actor, classroom):
        raise PermissionDenied
    if not classroom.is_active or not classroom.teacher_id or not classroom.teacher.is_active or not lesson.is_active or due_at < assigned_at:
        raise ValidationError('Kiểm tra lớp, giáo viên và thời hạn giao bài.')
    if not 1 <= repetitions <= 100:
        raise ValidationError('Số lượt viết mỗi từ phải từ 1 đến 100.')
    rubric = lesson_rubric(lesson, repetitions)
    assignment, created = ClassAssignment.objects.get_or_create(
        lesson=lesson, classroom=classroom,
        defaults=dict(created_by=actor, assigned_at=assigned_at, due_at=due_at, vocab_repetitions=repetitions,
                      rubric=rubric, reference_video=lesson.video_file.name,
                      allow_late_submission=allow_late_submission, requires_previous=requires_previous))
    if not created:
        raise ValidationError('Buổi học này đã được giao cho lớp. Không tạo trùng lượt giao.')
    from dashboard.integration import sync_class_assignment
    sync_class_assignment(assignment)
    return assignment

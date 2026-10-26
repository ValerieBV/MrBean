import re
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from accounts.permissions import can_assign_homework_to_class
from .models import ClassAssignment


def lesson_rubric(lesson, repetitions=1):
    data = {'description': lesson.description, 'skill': lesson.skill, 'title': lesson.title,
            'audio_name': lesson.audio_file.name if lesson.audio_file else ''}
    if lesson.skill == 'listening':
        questions = list(lesson.questions.values('id', 'question_text', 'option_a', 'option_b', 'option_c', 'option_d', 'correct_option', 'correct_answer'))
        if not questions or any(q['correct_option'] not in 'ABCD' or len(q['correct_option']) != 1 or not q['option_'+q['correct_option'].lower()] for q in questions):
            raise ValidationError('Mỗi câu nghe phải có lựa chọn và đáp án A–D hợp lệ trước khi giao bài.')
        data['questions'] = questions
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

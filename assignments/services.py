import re
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from accounts.permissions import can_assign_homework_to_class
from .models import ClassAssignment


def lesson_rubric(lesson, repetitions=1):
    data = {'description': lesson.description, 'skill': lesson.skill, 'title': lesson.title}
    if lesson.skill == 'listening':
        questions = list(lesson.questions.values('id', 'question_text', 'option_a', 'option_b', 'option_c', 'option_d', 'correct_option', 'correct_answer'))
        if not questions or any(q['correct_option'] not in 'ABCD' or len(q['correct_option']) != 1 or not q['option_'+q['correct_option'].lower()] for q in questions):
            raise ValidationError('Mỗi câu nghe phải có lựa chọn và đáp án A–D hợp lệ trước khi giao bài.')
        data['questions'] = questions
    elif lesson.skill == 'vocabulary':
        unique_words = {}
        for word in lesson.words.values_list('word', flat=True):
            if word.strip():
                unique_words.setdefault(re.sub(r'\s+', ' ', word.strip().casefold()), word.strip())
        words = list(unique_words.values())
        if not words:
            raise ValidationError('Chưa có từ vựng trong buổi học.')
        data.update(words=words, repetitions=repetitions)
    else:
        prompts = list(lesson.speaking_tasks.values_list('sentence', flat=True))
        if not prompts and not lesson.description.strip():
            raise ValidationError('Chưa có yêu cầu nội dung bài nói.')
        data['prompts'] = prompts
    return data


@transaction.atomic
def assign_to_class(*, actor, lesson, classroom, assigned_at, due_at, repetitions=1):
    if not can_assign_homework_to_class(actor, classroom):
        raise PermissionDenied
    if not classroom.is_active or not classroom.teacher_id or due_at < assigned_at:
        raise ValidationError('Kiểm tra lớp, giáo viên và thời hạn giao bài.')
    if not 1 <= repetitions <= 100:
        raise ValidationError('Số lượt viết mỗi từ phải từ 1 đến 100.')
    rubric = lesson_rubric(lesson, repetitions)
    assignment, created = ClassAssignment.objects.get_or_create(
        lesson=lesson, classroom=classroom,
        defaults=dict(created_by=actor, assigned_at=assigned_at, due_at=due_at, vocab_repetitions=repetitions, rubric=rubric))
    if not created:
        raise ValidationError('Buổi học này đã được giao cho lớp. Không tạo trùng lượt giao.')
    from dashboard.integration import sync_class_assignment
    sync_class_assignment(assignment)
    return assignment

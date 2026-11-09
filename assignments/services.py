import re
from datetime import datetime
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone
from accounts.permissions import can_assign_homework_to_class
from .models import ClassAssignment, Lesson, ListeningExercise, ListeningQuestion
from .listening import LISTENING_SPECS


@transaction.atomic
def import_vocabulary_rows(*, actor, lesson, rows):
    from django.db.models import Max
    from ai_core.permissions import is_manager
    from .models import VocabWord
    from .vocabulary_import import validate_vocabulary_rows, vocabulary_import_plan

    if not actor.is_authenticated or not actor.is_active:
        raise PermissionDenied
    lesson = Lesson.objects.select_for_update().get(pk=lesson.pk)
    if not (is_manager(actor) or actor.role == 'teacher' and lesson.created_by_id == actor.pk):
        raise PermissionDenied
    if lesson.skill != 'vocabulary':
        raise ValidationError('Chỉ nhập từ hàng loạt vào buổi Vocabulary.')
    if lesson.class_assignments.exists() or lesson.progress.exists():
        raise ValidationError('Buổi đã được sử dụng. Sao chép buổi trước khi thêm hoặc thay đổi từ vựng.')
    preview = vocabulary_import_plan(lesson, validate_vocabulary_rows(rows))
    additions = [row for row in preview if row['status'] == 'add']
    last = lesson.words.aggregate(value=Max('order'))['value'] or 0
    VocabWord.objects.bulk_create([
        VocabWord(lesson=lesson, order=last + index, **{field: row[field]
            for field in ('word', 'word_type', 'meaning', 'example')})
        for index, row in enumerate(additions, 1)
    ])
    return len(additions), len(preview) - len(additions)


def assignment_delete_block_reason(assignment):
    if assignment.tasks.filter(jobs__isnull=False).exists():
        return 'Lượt giao đã có bài nộp. Giữ lịch sử bài làm và kết quả; có thể tạm dừng nhận bài trong Hạn nộp & quy định.'
    if assignment.exemption_requests.exists() or assignment.tasks.filter(exemption__isnull=False).exists():
        return 'Lượt giao đã có đơn xin miễn. Giữ lịch sử xử lý và hạn mức miễn; có thể tạm dừng nhận bài trong Hạn nộp & quy định.'
    return ''


@transaction.atomic
def delete_class_assignment(*, actor, assignment):
    from accounts.models import Notification
    from courses.models import ClassRoom

    classroom = ClassRoom.objects.select_for_update().get(pk=assignment.classroom_id)
    if not can_assign_homework_to_class(actor, classroom):
        raise PermissionDenied
    locked = ClassAssignment.objects.select_for_update().filter(pk=assignment.pk, classroom=classroom).first()
    if locked is None:
        raise ValidationError('Lượt giao này đã được xóa. Tải lại danh sách bài tập đã giao.')
    task_ids = list(locked.tasks.select_for_update().order_by('pk').values_list('pk', flat=True))
    reason = assignment_delete_block_reason(locked)
    if reason:
        raise ValidationError(reason)
    try:
        locked.tasks.all().delete()
        locked.delete()
    except ProtectedError as exc:
        raise ValidationError('Lượt giao vừa phát sinh dữ liệu liên quan nên chưa thể xóa. Tải lại trang để kiểm tra lịch sử.') from exc
    Notification.objects.filter(event_key__in=[f'assignment:{pk}' for pk in task_ids]).delete()


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
        question.source_number = row.get('source_number') or row['number']
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
        problems = []
        if len(exercises) > 4:
            problems.append('Một buổi chỉ được giao từ 1 đến 4 bài nghe.')
        questions, groups = [], []
        if exercises:
            if lesson.questions.filter(exercise__isnull=True).exists():
                problems.append('Có câu hỏi chưa thuộc bài nghe. Mở quản lý bài tập để đưa câu hỏi vào đúng bài.')
            for exercise in exercises:
                items = list(exercise.questions.order_by('order', 'pk'))
                spec = LISTENING_SPECS.get(exercise.kind)
                if not spec:
                    problems.append(f'Bài {exercise.order}: dạng nghe không hợp lệ. Chọn lại dạng bài.')
                    continue
                expected = spec['count'] or exercise.question_count
                if len(items) != expected or [q.order for q in items] != list(range(1, expected + 1)):
                    problems.append(f'Bài {exercise.order} ({spec["label"]}) cần đủ {expected} câu, đánh số liên tục; hiện có {len(items)} câu. Nhập lại bảng đáp án của bài này.')
                if not exercise.audio_file:
                    problems.append(f'Bài {exercise.order}: chưa có file nghe. Tải file nghe trước khi giao.')
                elif not exercise.audio_file.storage.exists(exercise.audio_file.name):
                    problems.append(f'Bài {exercise.order}: file nghe không còn trên hệ thống. Tải lại file nghe.')
                if exercise.kind == 'part1' and not exercise.document_file:
                    problems.append(f'Bài {exercise.order} (Mô tả tranh): cần PDF đề bài có hình ảnh để xem trên web.')
                elif exercise.kind != 'part2' and exercise.document_file and not exercise.document_file.storage.exists(exercise.document_file.name):
                    problems.append(f'Bài {exercise.order}: file PDF không còn trên hệ thống. Tải lại PDF đề bài.')
                group = {'id': exercise.pk, 'order': exercise.order, 'kind': exercise.kind,
                    'label': exercise.get_kind_display(), 'title': exercise.display_title,
                    'question_count': len(items), 'audio_name': exercise.audio_file.name,
                    'document_name': exercise.document_file.name if exercise.kind != 'part2' else '', 'question_ids': [q.pk for q in items]}
                groups.append(group)
                for q in items:
                    row = {k: getattr(q, k) for k in ('id', 'question_text', 'option_a', 'option_b', 'option_c', 'option_d', 'correct_option', 'correct_answer')}
                    row.update(exercise_id=exercise.pk, exercise_order=exercise.order, number=q.order,
                        source_number=q.source_number,
                        choice_letters=exercise.choice_letters, requires_short_answer=True,
                        image_name=q.image.name if q.image else '')
                    questions.append(row)
        else:
            # Preserve source-branch lessons until their existing content is reorganized.
            questions = list(lesson.questions.values('id', 'question_text', 'option_a', 'option_b', 'option_c', 'option_d', 'correct_option', 'correct_answer'))
            for number, q in enumerate(questions, 1):
                q.update(number=number, choice_letters='ABCD', requires_short_answer=True)
        if not questions and not exercises:
            problems.append('Buổi nghe chưa có bài tập hoặc câu hỏi. Mở Quản lý bài tập, thêm từ 1 đến 4 bài nghe và nhập bảng đáp án trước khi giao.')
        legacy_ids = {exercise.pk for exercise in exercises if exercise.kind == 'legacy'}
        for q in questions:
            letters = q.get('choice_letters', 'ABCD')
            location = (f'Bài {q["exercise_order"]}, ' if q.get('exercise_order') else '') + f'câu {q["number"]}'
            if q.get('source_number'):
                location = (f'Bài {q["exercise_order"]}, ' if q.get('exercise_order') else '') + f'câu {q["source_number"]}'
            correct = q['correct_option']
            if len(correct) != 1 or correct not in letters:
                problems.append(f'{location}: chưa có đáp án đúng hợp lệ. Chỉ nhận {" / ".join(letters)}; nhập hoặc tải lại bảng đáp án.')
            elif not q['option_' + correct.lower()].strip():
                problems.append(f'{location}: thiếu lựa chọn {correct}. Bổ sung nội dung hoặc ký hiệu lựa chọn này.')
            if q.get('exercise_id') and q['exercise_id'] not in legacy_ids:
                missing = [letter for letter in letters if not q['option_' + letter.lower()].strip()]
                if missing:
                    problems.append(f'{location}: thiếu lựa chọn {" / ".join(missing)}. Dạng này cần đủ {" / ".join(letters)}.')
                exercise_kind = next((item.kind for item in exercises if item.pk == q['exercise_id']), '')
                if exercise_kind in ('part3','part4'):
                    if not q['question_text'].strip():
                        problems.append(f'{location}: thiếu nội dung câu hỏi. Đọc câu hỏi từ PDF hoặc nhập nội dung trước khi giao.')
                    placeholders = [letter for letter in letters if q['option_'+letter.lower()].strip() == letter]
                    if placeholders:
                        problems.append(f'{location}: cần nội dung đầy đủ cho lựa chọn {" / ".join(placeholders)}, không chỉ ký hiệu.')
        if problems:
            raise ValidationError(problems)
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
    from courses.models import ClassRoom
    # Authoring and publishing lock the same lesson; permission uses the current class teacher.
    classroom = ClassRoom.objects.select_for_update().get(pk=classroom.pk)
    lesson = Lesson.objects.select_for_update().get(pk=lesson.pk)
    if not can_assign_homework_to_class(actor, classroom):
        raise PermissionDenied
    if not classroom.is_active:
        raise ValidationError('Lớp đã ngừng hoạt động. Chọn lớp đang hoạt động để giao bài.')
    if not classroom.teacher_id or not classroom.teacher.is_active or classroom.teacher.role != 'teacher':
        raise ValidationError('Lớp cần có giáo viên đang hoạt động trước khi giao bài.')
    if not lesson.is_active:
        raise ValidationError('Buổi học đang ẩn. Mở buổi học trước khi giao.')
    if not all(isinstance(value, datetime) and timezone.is_aware(value) for value in (assigned_at, due_at)) or due_at < assigned_at:
        raise ValidationError('Hạn nộp không thể trước thời điểm mở bài. Kiểm tra lại ngày và giờ.')
    if ClassAssignment.objects.filter(lesson=lesson, classroom=classroom).exists():
        raise ValidationError('Buổi học này đã được giao cho lớp. Mở lượt giao hiện có để chỉnh hạn nộp, không tạo lại.')
    if lesson.skill != 'vocabulary':
        repetitions = 1
    if type(repetitions) is not int or not 1 <= repetitions <= 100:
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

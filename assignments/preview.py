"""A staff-only, answer-key-free summary of the exact checks used when assigning."""
from django.core.exceptions import ValidationError
from django.urls import reverse
from courses.models import Enrollment
from .models import ClassAssignment
from .services import lesson_rubric
from .listening import LISTENING_SPECS


def build_assignment_preview(lesson=None, classroom=None):
    data = {'lesson': None, 'classroom': None, 'ready': False, 'problems': [],
            'warnings': [], 'existing_assignment': None}
    if lesson:
        exercises = list(lesson.listening_exercises.all()) if lesson.skill == 'listening' else []
        data['lesson'] = {
            'title': lesson.title, 'order': lesson.order, 'skill': lesson.skill,
            'skill_label': lesson.get_skill_display(), 'program': lesson.get_program_display(),
            'content_url': reverse('assignments:lesson_detail', args=[lesson.pk]),
            'question_count': lesson.questions.count() if lesson.skill == 'listening' else 0,
            'legacy_listening': lesson.skill == 'listening' and not exercises and lesson.questions.exists(),
            'word_count': lesson.words.count() if lesson.skill == 'vocabulary' else 0,
            'exercises': [{'order': item.order, 'title': item.title or LISTENING_SPECS.get(item.kind, {}).get('label', 'Dạng chưa hợp lệ'),
                'kind': item.get_kind_display(), 'count': item.question_count,
                'choices': ' / '.join(item.choice_letters) if item.kind in ('part1','part2','part3','part4','legacy') else '',
                'has_audio': bool(item.audio_file), 'has_pdf': bool(item.document_file),
                'requires_pdf': item.kind == 'part1'} for item in exercises],
        }
        if lesson.skill == 'listening' and not exercises and lesson.questions.exists():
            data['warnings'].append('Buổi đang dùng cấu trúc nghe cũ. Kiểm tra nội dung và đáp án trong Quản lý bài tập trước khi giao.')
        try:
            rubric = lesson_rubric(lesson)
            if lesson.skill == 'vocabulary':
                data['lesson']['word_count'] = len(rubric['words'])
        except ValidationError as exc:
            data['problems'].extend(exc.messages)
        if not lesson.is_active:
            data['problems'].append('Buổi đang ẩn. Mở buổi học trước khi giao.')
    if classroom:
        teacher = classroom.teacher
        count = Enrollment.objects.filter(classroom=classroom, status='active', student__is_active=True).count()
        data['classroom'] = {'code': classroom.class_code, 'name': classroom.name,
            'teacher': (teacher.get_full_name() or teacher.username) if teacher else 'Chưa phân công',
            'student_count': count}
        if not classroom.is_active:
            data['problems'].append('Lớp đã ngừng hoạt động.')
        if not teacher or not teacher.is_active or teacher.role != 'teacher':
            data['problems'].append('Lớp cần có giáo viên đang hoạt động trước khi giao bài.')
        if not count:
            data['warnings'].append('Lớp chưa có học viên đang hoạt động. Lượt giao được lưu; học viên ghi danh sau sẽ nhận bài khi lượt giao còn mở và còn hạn.')
    if lesson and classroom:
        existing = ClassAssignment.objects.filter(lesson=lesson, classroom=classroom).first()
        if existing:
            data['existing_assignment'] = {'url': reverse('assignments:assigned_detail', args=[existing.pk])}
            data['problems'].insert(0, 'Buổi này đã giao cho lớp đã chọn. Mở lượt giao hiện có để xem bài hoặc chỉnh hạn nộp.')
    data['ready'] = bool(lesson and classroom and not data['problems'])
    return data

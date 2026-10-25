"""Integrated from B's _submit_listening, normalized to the reporting 0–10 scale."""
from django.core.exceptions import ValidationError


def grade_listening(questions, answers):
    if not questions or not isinstance(answers, dict):
        raise ValidationError('Bài nghe chưa có câu hỏi hoặc đáp án gửi lên không hợp lệ.')
    ids = {str(q['id']) for q in questions}
    if any(str(key) not in ids for key in answers):
        raise ValidationError('Có đáp án không thuộc bài nghe này.')
    details = []
    for q in questions:
        expected = q.get('correct_option', '')
        chosen = answers.get(str(q['id']), '')
        if expected not in ('A', 'B', 'C', 'D') or not isinstance(chosen, str) or chosen.strip().upper() not in ('', 'A', 'B', 'C', 'D'):
            raise ValidationError('Đáp án trắc nghiệm không hợp lệ.')
        chosen = chosen.strip().upper()
        details.append({'question_id': q['id'], 'chosen': chosen, 'correct': chosen == expected})
    correct = sum(row['correct'] for row in details)
    return {'score': round(correct / len(details) * 10, 2), 'correct_count': correct,
            'total': len(details), 'details': details, 'feedback': f'Đúng {correct}/{len(details)} câu. Chấm tự động theo đáp án.'}

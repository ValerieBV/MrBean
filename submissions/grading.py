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
        raw = answers.get(str(q['id']), '')
        if isinstance(raw, dict):
            if set(raw) - {'chosen', 'short_answer'}:
                raise ValidationError('Câu trả lời chứa trường không hợp lệ.')
            chosen, short_answer = raw.get('chosen', ''), raw.get('short_answer', '')
        else:
            chosen, short_answer = raw, ''
        choices = q.get('choice_letters', 'ABCD')
        if choices not in ('ABC', 'ABCD') or not isinstance(expected, str) or len(expected) != 1 or expected not in choices or not isinstance(chosen, str) or chosen.strip().upper() not in ('', *choices):
            raise ValidationError('Đáp án trắc nghiệm không hợp lệ.')
        if not isinstance(short_answer, str) or len(short_answer) > 255:
            raise ValidationError('Câu trả lời ngắn tối đa 255 ký tự.')
        chosen = chosen.strip().upper()
        short_answer = short_answer.strip()
        answered = bool(chosen) and (bool(short_answer) or not q.get('requires_short_answer', False))
        details.append({'question_id': q['id'], 'chosen': chosen, 'short_answer': short_answer,
            'answered': answered, 'correct': chosen == expected})
    correct = sum(row['correct'] for row in details)
    complete = all(row['answered'] for row in details)
    missing = sum(not row['answered'] for row in details)
    return {'score': round(correct / len(details) * 10, 2), 'correct_count': correct,
            'total': len(details), 'details': details, 'complete': complete, 'missing_count': missing,
            'feedback': f'Đúng {correct}/{len(details)} câu. ' + (
                'Đã làm đủ lựa chọn và câu trả lời theo yêu cầu.' if complete else f'Còn {missing} câu chưa làm đủ yêu cầu.')}

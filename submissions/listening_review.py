"""Published listening solutions, scoped to an immutable submitted attempt."""
from django.core.exceptions import ValidationError
from assignments.listening import FIRST_NUMBER
from assignments.listening_solutions import normalize_solutions
from assignments.models import ListeningExercise


def _bundle(exercise, questions, live):
    bundle = exercise.get('solutions')
    if not bundle:
        current = live.get(exercise.get('id'))
        if current is None or current.kind != exercise.get('kind') or current.audio_file.name != exercise.get('audio_name'):
            return {}
        saved = list(current.questions.all())
        if [(q.pk, q.correct_option, q.display_number) for q in saved] != [
                (q['id'], q.get('correct_option'), _number(q, exercise)) for q in questions]:
            return {}
        if current.kind in ('part3', 'part4') and any(
                getattr(saved_row, field) != snapshot.get(field, '')
                for saved_row, snapshot in zip(saved, questions)
                for field in ('question_text', 'option_a', 'option_b', 'option_c', 'option_d')):
            return {}
        bundle = current.solutions
    if not bundle:
        return {}
    try:
        bundle = normalize_solutions(bundle, exercise.get('kind'),
            expected_numbers=[_number(q, exercise) for q in questions])
    except ValidationError:
        return {}
    if [row['answer'] for row in bundle['questions']] != [q.get('correct_option') for q in questions]:
        return {}
    return bundle


def _number(question, exercise):
    return question.get('source_number') or FIRST_NUMBER.get(exercise.get('kind'), 1) + question.get('number', 1) - 1


def review_groups(job):
    if job.kind != 'listening' or job.status != 'graded':
        raise ValueError('published_listening_required')
    rubric = job.rubric_snapshot or {}
    exercises = rubric.get('exercises') or [{'id': None, 'order': 1, 'kind': 'legacy', 'title': job.task.title}]
    missing = [e['id'] for e in exercises if e.get('id') and not e.get('solutions')]
    live = {e.pk: e for e in ListeningExercise.objects.filter(pk__in=missing).prefetch_related('questions')}
    groups = []
    for exercise in exercises:
        questions = [q for q in rubric.get('questions', []) if q.get('exercise_id') == exercise['id']]
        if not questions:
            continue
        bundle = _bundle(exercise, questions, live)
        solutions = {q['number']: q for q in bundle.get('questions', [])}
        size = 3 if exercise.get('kind') in ('part3', 'part4') else 1
        for index in range(0, len(questions), size):
            section = questions[index:index+size]
            start, end = _number(section[0], exercise), _number(section[-1], exercise)
            passage = next((p for p in bundle.get('passages', []) if (p['start'], p['end']) == (start, end)), {})
            group = {'index': len(groups)+1, 'exercise': exercise, 'start': start, 'end': end,
                'label': f'Câu {start}–{end}' if size == 3 else f'Câu {start}',
                'passage': passage.get('text', ''), 'translation': passage.get('translation', ''), 'questions': []}
            for question in section:
                number = _number(question, exercise)
                solution = solutions.get(number, {})
                answer = job.answers.get(str(question['id']), {})
                if not isinstance(answer, dict):
                    answer = {'chosen': answer, 'short_answer': ''}
                chosen = str(answer.get('chosen', '')).upper()
                row = {'id': question['id'], 'number': number,
                    'question_text': solution.get('question_text') or question.get('question_text', ''),
                    'translation': solution.get('translation', ''),
                    'correct_option': question.get('correct_option', ''),
                    'chosen': chosen, 'short_answer': answer.get('short_answer', ''),
                    'correct': bool(chosen and chosen == question.get('correct_option')),
                    'explanation': solution.get('explanation', ''), 'options': []}
                for letter in question.get('choice_letters', 'ABCD'):
                    key = 'option_' + letter.lower()
                    text = solution.get(key) or question.get(key, '')
                    row['options'].append({'letter': letter, 'text': text,
                        'correct': letter == row['correct_option'], 'chosen': letter == chosen})
                group['questions'].append(row)
            groups.append(group)
    return groups


def focused_question(job, question_id):
    if type(question_id) is not int:
        raise ValueError('invalid_question')
    for group in review_groups(job):
        for question in group['questions']:
            if question['id'] == question_id:
                return {'question': question, 'group': group}
    raise ValueError('question_not_in_attempt')

"""Per-exercise attempts projected into the existing lesson completion history."""
from django.core.exceptions import ValidationError

from .grading import grade_listening


def latest_listening_submission(task):
    return task.jobs.filter(kind='listening', status='graded').order_by('-submitted_at', '-pk').first()


def submitted_exercise_ids(job):
    return {e['id'] for e in job.rubric_snapshot.get('exercises', [])} if job else set()


def grade_exercise_submission(task, rubric, answers, exercise_id=None):
    exercises = rubric.get('exercises', [])
    if not exercises:
        if exercise_id not in (None, '', 'legacy'):
            raise ValidationError('Bài nghe không hợp lệ.')
        return rubric, grade_listening(rubric.get('questions', []), answers)
    if exercise_id in (None, '') and len(exercises) == 1:
        exercise_id = exercises[0]['id']
    try:
        if type(exercise_id) not in (int, str):
            raise ValueError
        exercise_id = int(exercise_id)
    except (TypeError, ValueError):
        raise ValidationError('Chọn một bài nghe để nộp.')
    exercise = next((e for e in exercises if e['id'] == exercise_id), None)
    if exercise is None:
        raise ValidationError('Bài nghe không thuộc buổi học này.')
    questions = [q for q in rubric.get('questions', []) if q.get('exercise_id') == exercise_id]
    current = grade_listening(questions, answers)
    previous = latest_listening_submission(task)
    submitted = submitted_exercise_ids(previous) | {exercise_id}
    old_rubric = previous.rubric_snapshot if previous else {}
    old_questions = {q['id']: q for q in old_rubric.get('questions', [])}
    old_exercises = {e['id']: e for e in old_rubric.get('exercises', [])}
    selected_questions = [
        q if q.get('exercise_id') == exercise_id else old_questions.get(q['id'], q)
        for q in rubric.get('questions', []) if q.get('exercise_id') in submitted
    ]
    selected_exercises = [
        e if e['id'] == exercise_id else old_exercises.get(e['id'], e)
        for e in exercises if e['id'] in submitted
    ]
    merged = {str(q['id']): previous.answers.get(str(q['id']), '')
        for q in selected_questions if q.get('exercise_id') != exercise_id} if previous else {}
    merged.update({str(row['question_id']): {'chosen': row['chosen'], 'short_answer': row['short_answer']}
        for row in current['details']})
    result = grade_listening(selected_questions, merged)
    result['complete'] = result['complete'] and len(selected_exercises) == len(exercises)
    result['missing_count'] += len(rubric.get('questions', [])) - len(selected_questions)
    result.update(exercise_id=exercise_id, exercise_result=current,
        submitted_exercise_count=len(selected_exercises), exercise_count=len(exercises))
    result['feedback'] = f"Bài {exercise['order']}: {current['feedback']} Đã nộp {len(selected_exercises)}/{len(exercises)} bài nghe."
    snapshot = {**rubric, 'questions': selected_questions, 'exercises': selected_exercises,
        'submission_exercise_id': exercise_id, 'lesson_exercise_count': len(exercises)}
    return snapshot, result


def retain_other_drafts(task, submitted_questions):
    ids = {str(q['id']) for q in submitted_questions}
    draft = task.draft if task.draft_valid and isinstance(task.draft, dict) else {}
    remaining = {key: value for key, value in draft.get('answers', {}).items() if key not in ids}
    task.draft = {'text': '', 'answers': remaining} if remaining else {}
    if not remaining:
        task.draft_saved_at = None
    task.save(update_fields=['draft', 'draft_saved_at'])

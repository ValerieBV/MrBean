import io
import hashlib
import logging
from datetime import timedelta
from pathlib import Path
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from .models import GradingJob, VocabularyPage
from .providers import OpenAIGrader, validate_result
from .diagnostics import failure_reason

logger = logging.getLogger(__name__)


def prepare_image(upload):
    from PIL import Image, ImageOps, UnidentifiedImageError
    if upload.size > settings.AI_MAX_IMAGE_BYTES:
        raise ValidationError('Ảnh vượt 8 MiB.')
    try:
        with Image.open(upload) as image:
            if image.format not in ('PNG', 'JPEG', 'WEBP') or image.width * image.height > 20000000:
                raise ValidationError('Chỉ nhận PNG/JPEG/WebP tối đa 20 triệu điểm ảnh.')
            image = ImageOps.exif_transpose(image).convert('RGB')
            image.thumbnail((2400, 2400))
            stream = io.BytesIO()
            image.save(stream, format='JPEG', quality=90)
        return ContentFile(stream.getvalue(), name='vocabulary.jpg')
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValidationError('Không đọc được ảnh bài làm.') from exc


def enqueue_submission(*, task, submission_key, kind=None, text='', audio=None, reference_text='', answers=None, images=None, reference_version=None):
    if not isinstance(submission_key, str) or not submission_key.strip() or len(submission_key) > 128:
        raise ValidationError('Mã lần nộp không hợp lệ.')
    if not isinstance(text, str) or len(text) > 20000:
        raise ValidationError('Nội dung tối đa 20.000 ký tự.')
    images = images or []
    if len(images) > 5:
        raise ValidationError('Tối đa 5 ảnh mỗi lần nộp.')
    with transaction.atomic():
        task = type(task).objects.select_for_update().select_related('assignment__lesson', 'assignment__classroom').get(pk=task.pk)
        existing = GradingJob.objects.filter(submission_key=submission_key).first()
        if existing:
            if existing.task_id != task.pk:
                raise ValidationError('Mã lần nộp đã thuộc bài khác.')
            return existing, False
        from submissions.access import assert_can_submit
        assert_can_submit(task)
        if reference_version is not None and reference_version != task.assignment.reference_version:
            raise ValidationError('Yêu cầu bài đã được cập nhật. Tải lại trang để xem đúng mẫu trước khi nộp.')
        rubric = task.assignment.rubric if task.assignment_id else {}
        kind = rubric.get('skill', kind)
        if kind not in ('speaking', 'vocabulary', 'listening'):
            raise ValidationError('Loại bài không hợp lệ.')
        if kind == 'speaking':
            if text.strip() or not audio:
                raise ValidationError('Bài đọc theo video chỉ nhận ghi âm; không nhận transcript học viên nhập.')
            if rubric.get('mode') != 'repeat_video' or not rubric.get('reference_transcript') or not (rubric.get('video_embed_url') or rubric.get('video_name')):
                raise ValidationError('Giáo viên cần cập nhật video và lời mẫu cho lượt giao này trước khi nộp.')
        if kind == 'vocabulary':
            if not images:
                raise ValidationError('Cần chọn ít nhất 1 ảnh bài từ vựng trước khi nộp.')
            # Older open forms may still send text alongside photos; only photos
            # are evidence for new vocabulary submissions.
            text = ''
        if audio and (kind != 'speaking' or not 0 < audio.size <= settings.AI_MAX_AUDIO_BYTES or Path(audio.name).suffix.lower() not in ('.wav', '.mp3', '.m4a', '.webm', '.mp4', '.ogg')):
            raise ValidationError('File ghi âm không hợp lệ hoặc vượt 20 MiB.')
        if images and kind != 'vocabulary':
            raise ValidationError('Ảnh chỉ dùng cho bài từ vựng.')
        prepared = [prepare_image(image) for image in images]
        hashes = [hashlib.sha256(image.read()).hexdigest() for image in prepared]
        for image in prepared:
            image.seek(0)
        if len(set(hashes)) != len(hashes):
            raise ValidationError('Ảnh bị trùng; mỗi trang chỉ gửi một lần.')
        job = GradingJob(task=task, submission_key=submission_key, kind=kind, text=text,
                         rubric_snapshot=rubric, reference_text=reference_text)
        if audio:
            job.audio = audio
        if kind == 'listening':
            from submissions.grading import grade_listening
            result = grade_listening(rubric.get('questions', []), {} if answers is None else answers)
            job.answers = {str(row['question_id']): {'chosen': row['chosen'], 'short_answer': row['short_answer']} for row in result['details']}
            job.result = result
            job.status, job.grading_method, job.finished_at = 'graded', 'answer_key', timezone.now()
            job.teacher_feedback = result['feedback']
            job.completion_status = 'complete' if result['complete'] else 'incomplete'
            job.completion_confirmed_at = job.finished_at
        job.save()
        for image in prepared:
            VocabularyPage.objects.create(job=job, image=image)
        if task.assignment_id:
            from submissions.models import LessonProgress, QuestionResponse
            progress, _ = LessonProgress.objects.get_or_create(student=task.learner, lesson=task.assignment.lesson)
            if kind == 'listening':
                for row in job.result['details']:
                    QuestionResponse.objects.update_or_create(progress=progress, question_id=row['question_id'],
                        defaults={'chosen_option': row['chosen'], 'filled_text': row['short_answer'], 'is_correct': row['correct']})
            job.progress = progress
            job.save(update_fields=['progress'])
            from submissions.progress import sync_progress
            sync_progress(job, clear_draft=True)
        from accounts.notifications import notify
        from django.urls import reverse
        notify(recipient=task.assignment.classroom.teacher, sender=task.learner,
            title='Bài nộp mới: '+task.title, message=task.learner.get_full_name() or task.learner.username,
            target_url=reverse('submissions:result',args=[job.pk]), event_key=f'submission:{job.pk}')
        if job.status == 'graded':
            notify(recipient=task.learner, title='Đã có kết quả: '+task.title, message=job.teacher_feedback,
                target_url=reverse('submissions:result',args=[job.pk]), event_key=f'result:{job.pk}')
        return job, True


def expire_jobs(now=None):
    now = now or timezone.now()
    expired = GradingJob.objects.filter(status__in=['queued', 'processing'],
        submitted_at__lte=now-timedelta(seconds=settings.AI_DEADLINE_SECONDS)).update(
            status='manual', fallback_reason='ai_deadline_exceeded', finished_at=now)
    notify_manual_jobs()
    return expired


def notify_manual_jobs():
    from accounts.notifications import notify
    from accounts.models import Notification
    from django.db.models import Exists, OuterRef, Value, CharField
    from django.db.models.functions import Cast, Concat
    from django.urls import reverse
    rows = GradingJob.objects.filter(status='manual').annotate(
        notification_key=Concat(Value('manual:'),Cast('pk',output_field=CharField())),
        was_notified=Exists(Notification.objects.filter(event_key=OuterRef('notification_key')))).filter(was_notified=False)
    for job in rows.select_related('task__assignment__classroom__teacher','task__teacher'):
        teacher = job.task.assignment.classroom.teacher if job.task.assignment_id else job.task.teacher
        notify(recipient=teacher, title='Bài cần chấm thủ công: '+job.task.title,
            message='AI chưa hoàn tất. Vui lòng kiểm tra bài làm và xác nhận mức hoàn thành.',
            target_url=reverse('submissions:result',args=[job.pk]), event_key=f'manual:{job.pk}')


def process_job(job_id, provider=None):
    now = timezone.now()
    expire_jobs(now)
    if not GradingJob.objects.filter(pk=job_id, status='queued').update(status='processing', started_at=now):
        return False
    job = GradingJob.objects.get(pk=job_id)
    try:
        remaining = (job.ai_deadline - timezone.now()).total_seconds()
        if remaining <= 0:
            raise TimeoutError()
        raw = (provider or OpenAIGrader()).grade(job, timeout=min(settings.AI_REQUEST_TIMEOUT_SECONDS, remaining))
        if job.kind == 'vocabulary' and 'details' in raw:
            raw = {**raw, 'counts': [{'word': row['word'], 'count': row['observed']} for row in raw['details']]}
        result = validate_result(raw, job.kind, job.rubric_snapshot)
        transcript = raw.get('transcript', '') if job.kind == 'speaking' else ''
        if not isinstance(transcript, str) or len(transcript) > 20000:
            raise ValueError('invalid_transcript')
        finished = timezone.now()
        if finished >= job.ai_deadline:
            raise TimeoutError()
        if job.kind == 'speaking':
            result['transcript_source'] = 'openai_transcription'
        changed = GradingJob.objects.filter(pk=job_id, status='processing').update(
            status='ai_reviewed', result=result, suggested_score=None,
            transcript=transcript, grading_method='openai', finished_at=finished)
        if changed:
            from accounts.notifications import notify
            from django.urls import reverse
            teacher = job.task.assignment.classroom.teacher if job.task.assignment_id else job.task.teacher
            notify(recipient=teacher,title='AI đã đánh giá mức hoàn thành: '+job.task.title,
                message='Kiểm tra bản ghi hoặc ảnh và nhận xét trước khi xác nhận kết quả cuối cùng.',
                target_url=reverse('submissions:result',args=[job.pk]),event_key=f'ai-reviewed:{job.pk}')
    except Exception as exc:
        reason = failure_reason(exc)
        logger.warning('AI fallback job=%s reason=%s error_type=%s', job_id, reason, type(exc).__name__)
        GradingJob.objects.filter(pk=job_id, status='processing').update(
            status='manual', fallback_reason=reason,
            transcript=job.transcript if isinstance(job.transcript, str) and len(job.transcript)<=20000 else '', finished_at=timezone.now())
        notify_manual_jobs()
    return True

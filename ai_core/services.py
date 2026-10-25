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


def enqueue_submission(*, task, submission_key, kind=None, text='', audio=None, reference_text='', answers=None, images=None):
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
        rubric = task.assignment.rubric if task.assignment_id else {}
        kind = rubric.get('skill', kind)
        if kind not in ('speaking', 'vocabulary', 'listening'):
            raise ValidationError('Loại bài không hợp lệ.')
        if kind == 'speaking':
            if text.strip() or not audio:
                raise ValidationError('Bài đọc theo video chỉ nhận ghi âm; không nhận transcript học viên nhập.')
            if rubric.get('mode') != 'repeat_video' or not rubric.get('reference_transcript') or not rubric.get('video_embed_url'):
                raise ValidationError('Giáo viên cần cập nhật video và lời mẫu cho lượt giao này trước khi nộp.')
        if kind == 'vocabulary' and not text.strip() and not images:
            raise ValidationError('Cần văn bản hoặc ảnh bài từ vựng.')
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
            result = grade_listening(rubric.get('questions', []), answers or {})
            job.answers = {str(row['question_id']): row['chosen'] for row in result['details']}
            job.result, job.final_score = result, result['score']
            job.status, job.grading_method, job.finished_at = 'graded', 'answer_key', timezone.now()
            job.teacher_feedback = result['feedback']
        job.save()
        for image in prepared:
            VocabularyPage.objects.create(job=job, image=image)
        if task.assignment_id:
            from submissions.models import LessonProgress, QuestionResponse
            progress, _ = LessonProgress.objects.get_or_create(student=task.learner, lesson=task.assignment.lesson)
            if kind == 'listening':
                for row in job.result['details']:
                    QuestionResponse.objects.update_or_create(progress=progress, question_id=row['question_id'],
                        defaults={'chosen_option': row['chosen'], 'is_correct': row['correct']})
            progress.status, progress.completed_at, progress.draft = 'completed', job.submitted_at, {}
            progress.score = job.final_score * 10 if job.final_score is not None else None
            progress.save()
            job.progress = progress
            job.save(update_fields=['progress'])
        return job, True


def expire_jobs(now=None):
    now = now or timezone.now()
    return GradingJob.objects.filter(status__in=['queued', 'processing'],
        submitted_at__lte=now-timedelta(seconds=settings.AI_DEADLINE_SECONDS)).update(
            status='manual', fallback_reason='ai_deadline_exceeded', finished_at=now)


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
        GradingJob.objects.filter(pk=job_id, status='processing').update(
            status='ai_reviewed', result=result, suggested_score=result['score'],
            transcript=transcript, grading_method='openai', finished_at=finished)
    except Exception as exc:
        logger.warning('AI fallback job=%s error_type=%s', job_id, type(exc).__name__)
        GradingJob.objects.filter(pk=job_id, status='processing').update(
            status='manual', fallback_reason='ai_timeout' if isinstance(exc, TimeoutError) else 'ai_error',
            transcript=job.transcript if isinstance(job.transcript, str) and len(job.transcript)<=20000 else '', finished_at=timezone.now())
    return True

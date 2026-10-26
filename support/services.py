import logging
from datetime import timedelta
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from accounts.models import CustomUser
from accounts.notifications import notify
from courses.models import ClassRoom
from .ai import OpenAITutor, validate_answer
from .models import Conversation, Message, TutorAttempt
from .permissions import is_student, is_admin

logger = logging.getLogger(__name__)


def teacher_for(thread):
    teacher = thread.classroom.teacher if thread.classroom_id else thread.job.task.teacher if thread.job_id else None
    return teacher if teacher and teacher.is_active and teacher.role == 'teacher' else None


def validate_body(body):
    if not isinstance(body,str) or not 3 <= len(body.strip()) <= 4000:
        raise ValidationError('Nội dung cần có từ 3 đến 4000 ký tự.')
    return body.strip()


def own(thread, user):
    if not is_student(user) or thread.student_id != user.pk:
        raise PermissionDenied


def touch(thread):
    thread.updated_at=timezone.now()
    thread.save(update_fields=['status','recipient','recipient_role','escalated_at','updated_at'])


def system_message(thread, body):
    return Message.objects.create(conversation=thread, role='system', body=body)


def staff_can_reply(thread, user):
    human = thread.kind == Conversation.CONTACT or thread.escalated_at is not None
    if not human or not user.is_active:
        return False
    if is_admin(user):
        return True
    if thread.recipient_id != user.pk:
        return False
    if user.role=='manager':
        return thread.recipient_role=='management'
    if user.role=='teacher' and thread.recipient_role=='teacher':
        teacher=teacher_for(thread)
        return bool(teacher and teacher.pk==user.pk)
    return False


def start_study(student, job):
    if not is_student(student) or job.task.learner_id != student.pk:
        raise PermissionDenied
    if job.status != 'graded':
        raise ValidationError('Bạn có thể hỏi về bài này sau khi kết quả đã được công bố.')
    thread,_=Conversation.objects.get_or_create(student=student,job=job,kind=Conversation.KNOWLEDGE,
        defaults={'subject':('Giải đáp: '+job.task.title)[:180], 'classroom':job.task.assignment.classroom if job.task.assignment_id else None})
    return thread


def fail_stale(thread):
    TutorAttempt.objects.filter(conversation=thread,status='processing',
        created_at__lt=timezone.now()-timedelta(seconds=settings.AI_TUTOR_TIMEOUT_SECONDS+15)).update(
            status='failed',error_code='interrupted',finished_at=timezone.now())


def prepare_attempt(thread, question):
    fail_stale(thread)
    if thread.ai_attempts.filter(status='processing').exists():
        raise ValidationError('AI đang trả lời câu trước. Vui lòng chờ hoặc hỏi giáo viên.')
    if question.ai_attempts.filter(status='completed').exists():
        raise ValidationError('Câu hỏi này đã được trả lời.')
    if question.ai_attempts.count() >= 3:
        raise ValidationError('Đã thử lại câu này 3 lần. Bạn có thể hỏi giáo viên.')
    used=TutorAttempt.objects.filter(conversation__student=thread.student,created_at__date=timezone.localdate()).count()
    limited = used >= settings.AI_TUTOR_DAILY_LIMIT
    return TutorAttempt.objects.create(conversation=thread, question=question,
        status='failed' if limited else 'processing', error_code='daily_limit' if limited else '',
        finished_at=timezone.now() if limited else None)


def notify_new_message(thread, message, recipient):
    notify(recipient=recipient, sender=message.author, title='Trao đổi mới: '+thread.subject,
           message=message.body[:1000],target_url=thread.get_absolute_url(),event_key=f'support-message:{message.pk}')


def run_attempt(attempt, provider=None):
    if attempt.status != 'processing':
        return
    try:
        thread=Conversation.objects.select_related('student','job__task__learner','job__task__assignment').get(pk=attempt.conversation_id)
        if thread.status != Conversation.AI or thread.kind != Conversation.KNOWLEDGE:
            raise ValueError('conversation_handed_off')
        answer=validate_answer((provider or OpenAITutor()).answer(thread,attempt.question))
        with transaction.atomic():
            thread=Conversation.objects.select_for_update().get(pk=thread.pk)
            claimed=TutorAttempt.objects.filter(pk=attempt.pk,status='processing')
            if thread.status != Conversation.AI:
                claimed.update(status='cancelled',finished_at=timezone.now())
                return
            # The conditional update rejects a response after a handoff, retry,
            # closure or stale-request recovery.
            if not claimed.update(status='completed',route=answer['route'],finished_at=timezone.now()):
                return
            message=Message.objects.create(conversation=thread,role='assistant',body=answer['answer'])
            TutorAttempt.objects.filter(pk=attempt.pk).update(answer=message)
            touch(thread)
    except Exception as exc:
        logger.warning('Tutor attempt=%s error_type=%s',attempt.pk,type(exc).__name__)
        TutorAttempt.objects.filter(pk=attempt.pk,status='processing').update(
            status='failed',error_code='provider_error',finished_at=timezone.now())


def learner_message(thread, student, body, client_key, provider=None):
    own(thread,student); body=validate_body(body)
    attempt=None
    with transaction.atomic():
        thread=Conversation.objects.select_for_update().get(pk=thread.pk)
        previous=thread.messages.filter(client_key=client_key).first()
        if previous:
            if previous.author_id != student.pk or previous.body != body:
                raise ValidationError('Mã gửi đã được sử dụng. Tải lại trang trước khi gửi tiếp.')
            return previous
        if thread.status == Conversation.CLOSED:
            raise ValidationError('Cuộc trao đổi đã kết thúc. Mở lại để gửi câu hỏi.')
        if thread.messages.count() >= 200:
            raise ValidationError('Cuộc trao đổi đã dài. Vui lòng tạo liên hệ mới để tiếp tục.')
        if thread.status == Conversation.AI:
            fail_stale(thread)
            if thread.ai_attempts.filter(status='processing').exists():
                raise ValidationError('AI đang trả lời câu trước. Vui lòng chờ hoặc hỏi giáo viên.')
        message=Message.objects.create(conversation=thread,author=student,role='student',body=body,client_key=client_key)
        if thread.status == Conversation.AI:
            attempt=prepare_attempt(thread,message)
        else:
            thread.status=Conversation.WAITING
            notify_new_message(thread,message,thread.recipient)
        touch(thread)
    if attempt:
        run_attempt(attempt,provider)
    return message


def retry_question(thread, student, question_id, provider=None):
    own(thread,student)
    with transaction.atomic():
        thread=Conversation.objects.select_for_update().get(pk=thread.pk)
        if thread.status != Conversation.AI:
            raise ValidationError('Cuộc trao đổi hiện không ở chế độ hỏi AI.')
        question=thread.messages.filter(pk=question_id,role='student',author=student).first()
        latest=thread.messages.filter(role='student').last()
        if not question or not latest or question.pk != latest.pk:
            raise ValidationError('Chỉ thử lại câu hỏi gần nhất chưa được trả lời.')
        attempt=prepare_attempt(thread,question)
    run_attempt(attempt,provider)


def escalate(thread, student, note=''):
    own(thread,student)
    if len(note)>2000:
        raise ValidationError('Nội dung bổ sung tối đa 2000 ký tự.')
    with transaction.atomic():
        thread=Conversation.objects.select_for_update().select_related('classroom__teacher','job__task__teacher').get(pk=thread.pk)
        if thread.kind != Conversation.KNOWLEDGE:
            raise ValidationError('Liên hệ này đã được gửi trực tiếp cho người phụ trách.')
        if thread.status == Conversation.CLOSED:
            raise ValidationError('Mở lại cuộc trao đổi trước khi hỏi giáo viên.')
        if thread.escalated_at:
            return thread
        teacher=teacher_for(thread)
        if not teacher:
            raise ValidationError('Chưa có giáo viên phụ trách hoạt động. Vui lòng gửi Liên hệ & phản ánh đến quản lý.')
        thread.recipient=teacher;thread.recipient_role='teacher';thread.status=Conversation.WAITING
        thread.escalated_at=timezone.now()
        thread.ai_attempts.filter(status='processing').update(status='cancelled',finished_at=timezone.now())
        if note.strip():
            Message.objects.create(conversation=thread,author=student,role='student',body=note.strip())
        system_message(thread,'Học viên đã chuyển câu hỏi và lịch sử trao đổi cho giáo viên phụ trách.')
        touch(thread)
        notify(recipient=teacher,sender=student,title='Câu hỏi cần giải đáp: '+thread.subject,
               message='Học viên cần giáo viên giải thích thêm. Mở để xem câu hỏi và lịch sử trao đổi.',
               target_url=thread.get_absolute_url(),event_key=f'support-escalation:{thread.pk}')
    return thread


def create_contact(student, *, subject, category, target, job, body, client_key):
    if not is_student(student):
        raise PermissionDenied
    body=validate_body(body)
    if not 3 <= len(subject.strip()) <= 180 or category not in dict(Conversation.CATEGORY_CHOICES) or category=='knowledge':
        raise ValidationError('Tiêu đề hoặc loại phản ánh không hợp lệ.')
    if job and (job.task.learner_id != student.pk or job.status != 'graded'):
        raise PermissionDenied
    try:
        role,pk=target.split(':');pk=int(pk)
    except (ValueError,AttributeError):
        raise ValidationError('Chọn người nhận hợp lệ.')
    classroom=None
    if role=='teacher':
        classroom=ClassRoom.objects.filter(pk=pk,enrollments__student=student,teacher__is_active=True,
                                           teacher__role='teacher').select_related('teacher').first()
        recipient=classroom.teacher if classroom else None
    elif role=='management':
        recipient=CustomUser.objects.filter(Q(role__in=['admin','manager'])|Q(is_superuser=True),pk=pk,is_active=True).first()
    else:
        recipient=None
    if not recipient:
        raise ValidationError('Người nhận không còn phụ trách hoặc đang ngừng hoạt động. Vui lòng chọn lại.')
    if role=='teacher' and job:
        correct_class = job.task.assignment_id and job.task.assignment.classroom_id == classroom.pk
        legacy_teacher = not job.task.assignment_id and job.task.teacher_id == recipient.pk
        if not (correct_class or legacy_teacher):
            raise ValidationError('Chọn giáo viên của đúng lớp có kết quả này.')
    with transaction.atomic():
        thread,created=Conversation.objects.get_or_create(creation_key=client_key,defaults={
            'student':student,'kind':Conversation.CONTACT,'subject':subject.strip(),'category':category,
            'job':job,'classroom':classroom,'recipient':recipient,'recipient_role':role,'status':Conversation.WAITING})
        if thread.student_id != student.pk:
            raise PermissionDenied
        if not created:
            first=thread.messages.filter(role='student',client_key=client_key).first()
            changed=(thread.subject!=subject.strip() or thread.category!=category or
                     thread.job_id!=(job.pk if job else None) or not first or first.body!=body or
                     thread.recipient_role!=role or
                     (role=='teacher' and thread.classroom_id!=classroom.pk) or
                     (role=='management' and thread.recipient_id!=recipient.pk))
            if changed:
                raise ValidationError('Biểu mẫu này đã được gửi. Mở liên hệ cũ để bổ sung hoặc tải lại trang để tạo liên hệ mới.')
        if created:
            message=Message.objects.create(conversation=thread,author=student,role='student',body=body,client_key=client_key)
            notify_new_message(thread,message,recipient)
    return thread


def staff_message(thread, staff, body, client_key):
    body=validate_body(body)
    with transaction.atomic():
        thread=Conversation.objects.select_for_update().get(pk=thread.pk)
        if not staff_can_reply(thread,staff):
            raise PermissionDenied
        old=thread.messages.filter(client_key=client_key).first()
        if old:
            if old.author_id!=staff.pk or old.body!=body:
                raise ValidationError('Mã gửi đã được sử dụng. Tải lại trang trước khi gửi tiếp.')
            return old
        if thread.status==Conversation.CLOSED:
            raise ValidationError('Mở lại cuộc trao đổi trước khi trả lời.')
        message=Message.objects.create(conversation=thread,author=staff,role='staff',body=body,client_key=client_key)
        thread.status=Conversation.ANSWERED;touch(thread)
        notify_new_message(thread,message,thread.student)
    return message


def set_closed(thread,user,closed):
    with transaction.atomic():
        thread=Conversation.objects.select_for_update().get(pk=thread.pk)
        if not (is_student(user) and thread.student_id==user.pk) and not staff_can_reply(thread,user):
            raise PermissionDenied
        if closed and thread.status!=Conversation.CLOSED:
            thread.status=Conversation.CLOSED
            thread.ai_attempts.filter(status='processing').update(status='cancelled',finished_at=timezone.now())
            system_message(thread,'Cuộc trao đổi đã được đánh dấu kết thúc. Bạn có thể mở lại nếu còn thắc mắc.')
        elif not closed and thread.status==Conversation.CLOSED:
            thread.status=Conversation.WAITING if thread.kind==Conversation.CONTACT or thread.escalated_at else Conversation.AI
            message=system_message(thread,'Cuộc trao đổi đã được mở lại.')
            if is_student(user):notify_new_message(thread,message,thread.recipient)
        else:
            return
        touch(thread)

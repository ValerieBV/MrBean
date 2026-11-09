from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.urls import reverse

from .models import CustomUser, Notification


def user_delete_summary(user):
    from ai_core.models import GradingJob
    from dashboard.models import LearningTask
    from support.models import Conversation

    return {
        'tasks': LearningTask.objects.filter(learner=user).count(),
        'submissions': GradingJob.objects.filter(task__learner=user).count(),
        'conversations': Conversation.objects.filter(student=user).count(),
        'classes': user.teaching_classes.count(),
        'teaching_tasks': LearningTask.objects.filter(teacher=user).exclude(learner=user).count(),
    }


@transaction.atomic
def delete_user_account(*, actor, user_id, replacement_teacher=None):
    from ai_core.models import GradingJob
    from courses.models import ClassRoom
    from dashboard.models import LearningTask
    from support.models import Conversation, Message

    if not actor.is_authenticated or not actor.is_active or not actor.is_admin_user:
        raise PermissionDenied
    admins = list(CustomUser.objects.select_for_update().filter(
        Q(role='admin') | Q(is_superuser=True)).order_by('pk'))
    target = CustomUser.objects.select_for_update().get(pk=user_id)
    if target.pk == actor.pk:
        raise ValidationError('Không thể tự xóa tài khoản đang đăng nhập.')
    if target.is_admin_user and not any(user.is_active and user.pk != target.pk for user in admins):
        raise ValidationError('Cần giữ ít nhất một quản trị viên đang hoạt động.')

    teaching_tasks = list(LearningTask.objects.select_for_update().filter(teacher=target).exclude(learner=target))
    needs_replacement = bool(teaching_tasks) or ClassRoom.objects.filter(teacher=target).exists()
    replacement = None
    if needs_replacement:
        replacement = CustomUser.objects.select_for_update().filter(
            pk=getattr(replacement_teacher, 'pk', None), role='teacher', is_active=True).exclude(pk=target.pk).first()
        if replacement is None:
            raise ValidationError('Chọn giáo viên đang hoạt động để tiếp nhận lớp và bài tập trước khi xóa tài khoản.')

    owned_tasks = list(LearningTask.objects.select_for_update().filter(learner=target).values_list('pk', flat=True))
    job_ids = list(GradingJob.objects.filter(task_id__in=owned_tasks).values_list('pk', flat=True))
    threads = list(Conversation.objects.filter(student=target))
    removed_urls = [reverse('submissions:do_task', args=[pk]) for pk in owned_tasks]
    removed_urls += [reverse('submissions:result', args=[pk]) for pk in job_ids]
    removed_urls += [thread.get_absolute_url() for thread in threads]

    if replacement:
        ClassRoom.objects.filter(teacher=target).update(teacher=replacement)
        for task in LearningTask.objects.filter(pk__in=[task.pk for task in teaching_tasks]).select_related('assignment__classroom'):
            current_teacher = task.assignment.classroom.teacher_id if task.assignment_id else None
            task.teacher_id = current_teacher if current_teacher and current_teacher != target.pk else replacement.pk
            LearningTask.objects.filter(pk=task.pk).update(teacher_id=task.teacher_id)

    # Other learners keep their conversations and the messages this user sent them.
    Message.objects.filter(author=target).exclude(conversation__student=target).update(author=None)
    Conversation.objects.filter(recipient=target).exclude(student=target).update(
        recipient=actor, recipient_role='management')
    try:
        Conversation.objects.filter(student=target).delete()
        GradingJob.objects.filter(pk__in=job_ids).delete()
        LearningTask.objects.filter(pk__in=owned_tasks).delete()
        Notification.objects.filter(target_url__in=removed_urls).delete()
        target.delete()
    except ProtectedError as exc:
        raise ValidationError('Tài khoản còn liên kết với dữ liệu của người dùng khác. Chuyển người phụ trách hoặc xử lý liên kết đó trước khi xóa.') from exc

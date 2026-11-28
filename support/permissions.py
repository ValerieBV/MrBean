from django.db.models import Q
from .models import Conversation


def is_student(user):
    return user.is_authenticated and user.is_active and user.role == 'student' and not user.is_superuser


def is_admin(user):
    return user.is_superuser or user.role == 'admin'


def conversations_for(user):
    rows = Conversation.objects.select_related('student', 'recipient', 'classroom__teacher', 'job__task__learner')
    if is_student(user):
        return rows.filter(student=user)
    # Unescalated AI discussions remain private to their learner.
    human = Q(kind=Conversation.CONTACT) | Q(escalated_at__isnull=False)
    if is_admin(user):
        return rows.filter(human)
    if user.role == 'teacher':
        current=Q(classroom__teacher=user)|Q(classroom__isnull=True,job__task__teacher=user)
        return rows.filter(human,current,recipient=user,recipient_role='teacher')
    if user.role == 'manager':
        return rows.filter(human,recipient=user,recipient_role='management')
    return rows.none()

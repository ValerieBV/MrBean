from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from accounts.notifications import notify
from courses.models import ClassRoom
from .models import Conversation


@receiver(post_save, sender=ClassRoom)
def transfer_class_questions(sender, instance, **kwargs):
    """Teacher-routed discussions follow the current class teacher."""
    if kwargs.get('raw'):
        return
    teacher = instance.teacher if instance.teacher_id and instance.teacher.is_active and instance.teacher.role=='teacher' else None
    rows = Conversation.objects.filter(classroom=instance, recipient_role='teacher').exclude(recipient=teacher)
    for thread in rows:
        thread.recipient = teacher
        thread.updated_at = timezone.now()
        thread.save(update_fields=['recipient', 'updated_at'])
        if teacher and thread.status != Conversation.CLOSED:
            notify(recipient=teacher, title='Trao đổi của lớp mới phụ trách: '+thread.subject,
                   message='Có cuộc trao đổi cần tiếp tục theo dõi.', target_url=thread.get_absolute_url(),
                   event_key=f'support-transfer:{thread.pk}:{teacher.pk}:{thread.updated_at.isoformat()}')

"""Internal application notifications, deduplicated per business event."""
from .models import Notification


def notify(*, recipient, title, message, target_url='', sender=None, event_key=None, kind='system'):
    if not recipient or not recipient.is_active:
        return None
    values = dict(recipient=recipient, sender=sender, title=title[:255], message=message,
                  target_url=target_url, notification_type=kind)
    if event_key:
        return Notification.objects.get_or_create(event_key=event_key, defaults=values)[0]
    return Notification.objects.create(**values)

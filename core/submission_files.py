"""Remove private submission files only after their last database reference commits."""
import logging

from django.db import transaction
from django.db.models.signals import post_delete

logger = logging.getLogger(__name__)
SUBMISSION_PREFIXES = ('ai_submissions/', 'submissions/recordings/')


def submission_file_fields():
    from ai_core.models import GradingJob, VocabularyPage
    from submissions.models import SpeakingRecording
    return ((GradingJob, 'audio'), (VocabularyPage, 'image'), (SpeakingRecording, 'audio'))


def file_is_referenced(name, using='default'):
    return any(model.objects.using(using).filter(**{field: name}).exists()
        for model, field in submission_file_fields())


def schedule_file_removal(sender, instance, using, **kwargs):
    field_name = next(field for model, field in submission_file_fields() if model is sender)
    field = getattr(instance, field_name)
    name, storage = field.name, field.storage
    if not name or not name.startswith(SUBMISSION_PREFIXES):
        return

    def remove_unreferenced():
        if not file_is_referenced(name, using):
            try:
                storage.delete(name)
            except OSError:
                logger.exception('Could not remove unreferenced submission file: %s', name)

    transaction.on_commit(remove_unreferenced, using=using, robust=True)


def register_submission_cleanup():
    for model, _ in submission_file_fields():
        post_delete.connect(schedule_file_removal, sender=model,
            dispatch_uid=f'submission-file-cleanup:{model._meta.label_lower}')

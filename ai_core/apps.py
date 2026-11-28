from django.apps import AppConfig


class AiCoreConfig(AppConfig):
    name = 'ai_core'

    def ready(self):
        from core.submission_files import register_submission_cleanup
        register_submission_cleanup()

from django.apps import AppConfig


class CoursesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'courses'
    verbose_name = 'Quản lý Khóa học & Lớp học'

    def ready(self):
        import courses.signals  # noqa

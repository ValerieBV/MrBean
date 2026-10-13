from django.contrib import admin
from .models import LearningTask


@admin.register(LearningTask)
class LearningTaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'assignment_key', 'learner', 'teacher', 'due_at')
    list_filter = ('teacher',)
    search_fields = ('title', 'assignment_key', 'learner__username')

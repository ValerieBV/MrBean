from django.contrib import admin

from .models import LessonProgress, QuestionResponse, SpeakingRecording


@admin.register(LessonProgress)
class LessonProgressAdmin(admin.ModelAdmin):
    list_display = ("student", "lesson", "status", "score", "completed_at")
    list_filter = ("status", "lesson__skill")
    search_fields = ("student__username",)


admin.site.register(QuestionResponse)
admin.site.register(SpeakingRecording)

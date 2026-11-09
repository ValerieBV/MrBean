from django.contrib import admin

from .models import LessonProgress, QuestionResponse, SpeakingRecording


@admin.register(LessonProgress)
class LessonProgressAdmin(admin.ModelAdmin):
    list_display = ("student", "lesson", "status", "completed_at")
    exclude = ("score",)
    list_filter = ("status", "lesson__skill")
    search_fields = ("student__username",)


admin.site.register(QuestionResponse)
admin.site.register(SpeakingRecording)

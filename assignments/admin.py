from django.contrib import admin

from .models import Lesson, VocabWord, ListeningQuestion, SpeakingTask

admin.site.site_header = "Mr Bean English"
admin.site.site_title = "Mr Bean English"
admin.site.index_title = "Quản trị hệ thống"


class VocabWordInline(admin.TabularInline):
    model = VocabWord
    extra = 1


class ListeningQuestionInline(admin.StackedInline):
    model = ListeningQuestion
    extra = 1


class SpeakingTaskInline(admin.TabularInline):
    model = SpeakingTask
    extra = 1


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ("skill", "program", "order", "title", "item_count", "is_active")
    list_filter = ("skill", "program", "is_active")
    search_fields = ("title", "description")
    inlines = [VocabWordInline, ListeningQuestionInline, SpeakingTaskInline]

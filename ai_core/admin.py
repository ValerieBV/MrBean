from django.contrib import admin
from .models import GradingJob


@admin.register(GradingJob)
class GradingJobAdmin(admin.ModelAdmin):
    list_display = ('submission_key', 'task', 'kind', 'status', 'submitted_at', 'completion_status')
    list_filter = ('status', 'kind')
    search_fields = ('submission_key',)
    readonly_fields = [field.name for field in GradingJob._meta.fields if field.name not in ('suggested_score','final_score')]
    exclude = ('suggested_score','final_score')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

from django.contrib import admin
from .models import Conversation, Message, TutorAttempt
from .permissions import conversations_for


class ReadOnlyAdmin(admin.ModelAdmin):
    def get_queryset(self,request):
        rows=super().get_queryset(request)
        allowed=conversations_for(request.user)
        return rows.filter(pk__in=allowed) if self.model==Conversation else rows.filter(conversation__in=allowed)
    def has_add_permission(self,request):return False
    def has_change_permission(self,request,obj=None):return False
    def has_delete_permission(self,request,obj=None):return False


@admin.register(Conversation)
class ConversationAdmin(ReadOnlyAdmin):
    list_display=['subject','kind','student','recipient','status','updated_at']
    list_filter=['kind','status','recipient_role']
    search_fields=['subject','student__username']


@admin.register(Message)
class MessageAdmin(ReadOnlyAdmin):
    list_display=['conversation','role','author','created_at']


@admin.register(TutorAttempt)
class TutorAttemptAdmin(ReadOnlyAdmin):
    list_display=['conversation','status','route','error_code','created_at']

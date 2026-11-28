from django.urls import path
from django.views.generic import RedirectView
from . import views
from .models import Conversation

app_name='support'
urlpatterns=[
    path('',RedirectView.as_view(pattern_name='support:contact_list',permanent=False)),
    path('hoi-dap/',views.knowledge_list,name='knowledge_list'),
    path('lien-he/',views.thread_list,{'kind':Conversation.CONTACT},name='contact_list'),
    path('lien-he/moi/',views.contact_new,name='contact_new'),
    path('ket-qua/<int:job_id>/hoi-ai/',views.start,name='start'),
    path('ket-qua/<int:job_id>/cau/<int:question_id>/hoi-ai/',views.start,name='start_question'),
    path('trao-doi/<int:pk>/',views.detail,name='detail'),
    path('trao-doi/<int:pk>/gui/',views.reply,name='reply'),
    path('trao-doi/<int:pk>/hoi-giao-vien/',views.handoff,name='handoff'),
    path('trao-doi/<int:pk>/thu-lai/',views.retry,name='retry'),
    path('trao-doi/<int:pk>/ket-thuc/',views.close,name='close'),
]

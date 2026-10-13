from django.urls import path
from . import views

app_name = 'ai_core'
urlpatterns = [
    path('submissions/', views.submit, name='submit'),
    path('jobs/<int:job_id>/', views.detail, name='detail'),
    path('jobs/<int:job_id>/audio/', views.audio, name='audio'),
    path('jobs/<int:job_id>/review/', views.review, name='review'),
]

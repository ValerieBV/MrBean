from django.urls import path
from . import views
app_name = 'ai_core'
urlpatterns = [
    path('submissions/', views.submit, name='submit'),
    path('jobs/<int:job_id>/', views.detail, name='detail'),
    path('jobs/<int:job_id>/audio/', views.audio, name='audio'),
    path('jobs/<int:job_id>/reference-video/', views.reference_video, name='reference_video'),
    path('jobs/<int:job_id>/review/', views.review, name='review'),
    path('jobs/<int:job_id>/completion/', views.confirm_completion, name='confirm_completion'),
    path('pages/<int:page_id>/', views.image, name='image'),
    path('jobs/<int:job_id>/listening/<int:exercise_id>/<str:kind>/', views.listening_material, name='listening_material'),
]
